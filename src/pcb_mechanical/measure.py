"""Linux resource accounting and pressure guards around one owned process tree."""
import argparse
import os
import resource
import shutil
import signal
import subprocess
import time
from pathlib import Path
from .common import write_json


def tree_rss(pid):
    try:
        status=Path(f'/proc/{pid}/status').read_text()
        own=next((int(line.split()[1])*1024 for line in status.splitlines() if line.startswith('VmRSS:')),0)
        children=Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
        return own+sum(tree_rss(int(child)) for child in children)
    except (OSError,ValueError):return 0


def available_memory():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):return int(line.split()[1])*1024
    raise RuntimeError('Linux MemAvailable is required for the host-memory guard')


def stop(process):
    if process.poll() is not None:return
    os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL);process.wait()


class DeviceMemory:
    """Conservative device-wide guard; includes desktop usage, stops only our child."""
    def __init__(self):
        import ctypes
        self.ctypes=ctypes;self.lib=ctypes.CDLL('libnvidia-ml.so.1')
        self.device=ctypes.c_void_p()
        if self.lib.nvmlInit_v2()!=0 or self.lib.nvmlDeviceGetHandleByIndex_v2(0,ctypes.byref(self.device))!=0:
            raise RuntimeError('NVIDIA memory accounting unavailable')
    def used(self):
        c=self.ctypes
        class Memory(c.Structure):_fields_=[('total',c.c_ulonglong),('free',c.c_ulonglong),('used',c.c_ulonglong)]
        memory=Memory()
        if self.lib.nvmlDeviceGetMemoryInfo(self.device,c.byref(memory))!=0:raise RuntimeError('NVIDIA memory query failed')
        return memory.used


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('destination',type=Path)
    p.add_argument('--max-rss-gib',type=float,default=0)
    p.add_argument('--max-gpu-gib',type=float,default=0)
    p.add_argument('--min-available-gib',type=float,default=1.5)
    p.add_argument('--min-disk-gib',type=float,default=2)
    p.add_argument('--heartbeat',type=Path)
    # parse_known_args keeps the executable's arguments intact after --.
    a,args=p.parse_known_args()
    if args and args[0]=='--':args=args[1:]
    if not args:p.error('A command is required after --')
    dest=a.destination;limit=a.max_rss_gib*1024**3
    start=time.monotonic();free_before=shutil.disk_usage(dest.parent).free
    available_before=available_memory();peak=0;minimum_available=available_before;reason=None
    process=None;gpu=DeviceMemory() if a.max_gpu_gib else None;gpu_peak=0
    def interrupted(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    try:
        if available_before<a.min_available_gib*1024**3:
            reason='insufficient_host_memory_before_start'
        else:
            process=subprocess.Popen(args,start_new_session=True)
            while process.poll() is None:
                if a.heartbeat:a.heartbeat.touch()
                peak=max(peak,tree_rss(process.pid))
                if gpu:gpu_peak=max(gpu_peak,gpu.used())
                available=available_memory();minimum_available=min(minimum_available,available)
                if gpu and gpu_peak>a.max_gpu_gib*1024**3:reason='device_memory_limit'
                elif limit and peak>limit:reason='process_tree_rss_limit'
                elif available<a.min_available_gib*1024**3:reason='host_memory_pressure'
                elif shutil.disk_usage(dest.parent).free<a.min_disk_gib*1024**3:reason='disk_reserve'
                if reason:stop(process);break
                time.sleep(.5)
    except KeyboardInterrupt:
        reason='interrupted'
    finally:
        if process:stop(process)
        usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        code=process.returncode if process else 125
        if reason:print('Command stopped: '+reason,flush=True)
        write_json(dest,{'command':args,'exit_code':code,'wall_seconds':time.monotonic()-start,
                        'cpu_user_seconds':usage.ru_utime,'cpu_system_seconds':usage.ru_stime,
                        'peak_process_tree_rss_bytes_sampled':peak,'sampling_interval_s':.5,
                        'peak_device_used_bytes':gpu_peak if gpu else None,'device_limit_gib':a.max_gpu_gib or None,
                        'device_accounting':'Conservative total device usage, including other applications' if gpu else None,
                        'rss_limit_bytes':limit or None,'memory_limit_exceeded':reason=='process_tree_rss_limit',
                        'stop_reason':reason,'host_memory_reserve_bytes':a.min_available_gib*1024**3,
                        'minimum_host_available_bytes':minimum_available,
                        'free_disk_before_bytes':free_before,'free_disk_after_bytes':shutil.disk_usage(dest.parent).free})
    return (130 if reason=='interrupted' else (125 if reason else (128-code if code<0 else code)))


if __name__=='__main__':raise SystemExit(main())
