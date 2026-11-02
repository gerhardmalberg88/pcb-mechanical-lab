"""Real solver and analytical validation, with persisted numerical evidence."""
from pathlib import Path
import json,math,time
from .common import ROOT,write_json,read_config,call,WorkflowError,serial_workflow
from .config import load
from .pipeline import run_case
from .runtime import Runtime

@serial_workflow
def doctor(backend='cpu',full=False):
 rt=Runtime();selected,reason=rt.select(backend);root=ROOT/'results/validation'/selected;root.mkdir(parents=True,exist_ok=True)
 checks={};start=time.monotonic()
 try:
  for kind,command in [('cpu',['ElmerSolver','-v']),('cpu',['ElmerGrid']),('cpu',['gmsh','-version']),('tools',['pvpython','--version'])]:
   key=' '.join(command);r=rt.run(kind,command,capture=True,check=False);checks[key]={'exit_code':r.returncode,'output':(r.stdout+r.stderr)[-2500:]}
  if selected=='cuda':
   rt.run('cuda',['/opt/psd-python/bin/python','-c','from pcb_mechanical.psd import backend_module; print(backend_module("cuda")[1])'],gpu_count=1,capture=True)
   checks['cupy_device']='passed'
  rt.run('cpu',['/usr/bin/python3','-m','unittest','discover','-s','/workflow/tests','-v'],output=root,log=root/'tests.log')
  checks['unit_tests']='passed'
  if full:
   for variant,size in [('coarse',3.),('fine',2.)]:
    c=load(ROOT/'examples/cantilever/case.json');c.update(output=str(root/variant));c['mesh']['size_mm']=size;c['execution']['backend']=selected
    out,status=run_case(c);checks[variant]={'status':status['status'],'wall_seconds':status['wall_seconds']}
    if status['status']!='complete':raise WorkflowError(f'{variant} example incomplete')
   coarse=read_config(root/'coarse/modal/modal-summary.json');fine=read_config(root/'fine/modal/modal-summary.json')
   theoretical=1.875104068711961**2/(2*math.pi*.1**2)*.0016/math.sqrt(12)*math.sqrt(24.37e9/1944)
   errors=[abs(d['frequencies_hz'][0]/theoretical-1) for d in [coarse,fine]]
   checks['cantilever']={'analytical_hz':theoretical,'coarse_hz':coarse['frequencies_hz'][0],'fine_hz':fine['frequencies_hz'][0],'relative_errors':errors,'accepted':max(errors)<.02}
   if not checks['cantilever']['accepted']:raise WorkflowError('Cantilever analytical comparison failed')
   rt.run('cpu',['/usr/bin/python3','-m','pcb_mechanical.compare','/work/coarse','/work/fine','/work/mesh-comparison.json'],output=root,log=root/'mesh-comparison.log')
   checks['mesh_comparison']=read_config(root/'mesh-comparison.json')

   if selected=='cuda' and (ROOT/'results/validation/cpu/coarse/modal/modal.npz').exists():
    rt.run('cpu',['/usr/bin/python3','-m','pcb_mechanical.compare','/work/cpu/coarse','/work/cuda/coarse','/work/backend-comparison.json','--backends'],output=ROOT/'results/validation',log=root/'backend-comparison.log')
    checks['backend_comparison']=read_config(ROOT/'results/validation/backend-comparison.json')
    if not checks['backend_comparison']['accepted']:raise WorkflowError('CPU/CUDA numerical comparison failed')
   # The example acceptance is analytical/mesh frequency convergence. Full RMS
   # mesh acceptance is a separate mandatory board-study gate. Keep diagnostics.
   checks['mesh_frequency_accepted']=checks['mesh_comparison']['maximum_frequency_change']<.02
   if not checks['mesh_frequency_accepted']:raise WorkflowError('Cantilever frequency mesh refinement check failed')
  status='passed'
 except (WorkflowError,OSError,ValueError) as e:status='failed';checks['error']=str(e)
 write_json(root/'doctor.json',{'status':status,'backend':selected,'reason':reason,'checks':checks,'wall_seconds':time.monotonic()-start})
 print(json.dumps({'status':status,'evidence':str(root/'doctor.json')},indent=2))
 return 0 if status=='passed' else 1
