"""Immutable input snapshots, artifact caching, bounded owned-container execution."""
from pathlib import Path
from contextlib import contextmanager
import os,signal,time,uuid,shutil,json
from .common import ROOT,digest,fingerprint,write_json,read_config,WorkflowError,serial_workflow
from .config import load,validate
from .runtime import Runtime
STAGES=['extract','mesh','convert','modal','psd','postprocess']

@contextmanager
def deadline(seconds):
 def expired(signum,frame):raise WorkflowError('Study wall-clock budget exhausted')
 prior=signal.signal(signal.SIGALRM,expired);old=signal.getitimer(signal.ITIMER_REAL)
 signal.setitimer(signal.ITIMER_REAL,min(seconds,old[0]) if old[0]>0 else seconds)
 started=time.monotonic()
 try:yield
 finally:
  signal.setitimer(signal.ITIMER_REAL,max(.001,old[0]-(time.monotonic()-started)) if old[0]>0 else 0,old[1]);signal.signal(signal.SIGALRM,prior)

def files(path):
 return {str(p.relative_to(path)):digest(p) for p in sorted(Path(path).rglob('*')) if p.is_file() and not p.is_symlink()}

def implementation():
 paths=[p for folder in ['src','scripts','containers','env'] for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts and 'locks' not in p.parts and not any(part.endswith('.egg-info') for part in p.parts)]
 return fingerprint({str(p.relative_to(ROOT)):digest(p) for p in paths+[ROOT/'pyproject.toml',ROOT/'pcb-mechanical']})

def check_output(board,out):
 board=Path(board).resolve();out=Path(out).resolve()
 for parent in board.parents:
  if (parent/'.git').is_file() or (parent/'.git/HEAD').is_file():
   if parent!=ROOT and (out==parent or parent in out.parents):raise WorkflowError('Output must stay outside the source hardware repository')
   break
 if out==board.parent or out in board.parents:raise WorkflowError('Output must not contain the source board')

def prepare(c):
 out=Path(c['output']);board=Path(c['board']);check_output(board,out)
 if out.exists() and any(out.iterdir()) and not (out/'.pcb-mechanical-owned').exists():raise WorkflowError('Output is nonempty and not owned by PCB Mechanical Lab')
 out.mkdir(parents=True,exist_ok=True);(out/'.pcb-mechanical-owned').touch()
 inp=out/'input';inp.mkdir(exist_ok=True)
 before=digest(board);data=board.read_bytes()
 import hashlib
 if hashlib.sha256(data).hexdigest()!=before or digest(board)!=before:raise WorkflowError('Board changed during snapshot; retry after saving')
 (inp/'board.kicad_pcb').write_bytes(data)
 for parent in board.parents:
  lic=parent/'LICENSE'
  if lic.is_file():shutil.copy2(lic,inp/'LICENSE');break
 write_json(inp/'provenance.json',{'source_board':str(board),'sha256':before,'policy':'Source opened read-only; no source Git operations; immutable per-run snapshot'})
 frozen={k:v for k,v in c.items() if k not in ('case_file','output')};frozen['board']='input/board.kicad_pcb'
 write_json(out/'case.json',frozen)
 return out,before,frozen

@serial_workflow
def run(case_path,stage='all',backend=None,force=False,time_budget_minutes=None):
 c=load(case_path)
 if backend:c['execution']['backend']=backend
 if time_budget_minutes is not None:c['execution']['time_budget_minutes']=time_budget_minutes
 return run_case(validate(c),stage,force)

def run_case(c,stage='all',force=False):
 start=time.monotonic();out,source,frozen=prepare(c);rt=Runtime();owner=uuid.uuid4().hex
 old_owner=os.environ.get('PCB_MECHANICAL_BATCH_ID');os.environ['PCB_MECHANICAL_BATCH_ID']=owner
 status={'status':'running','source_sha256':source,'case':frozen,'stages':{},'started_unix':time.time()}
 try:
  with deadline(c['execution']['time_budget_minutes']*60-20):
   selected,reason=rt.select(c['execution']['backend']);status.update(backend=selected,backend_reason=reason)
   print(reason,flush=True)
   images={kind:rt.image_id(kind) for kind in set(['cpu','tools',selected])};status['images']=images;rt.pinned_images=images
   base={'case':frozen,'source':source,'implementation':implementation(),'backend':selected,'images':images}
   cache=read_config(out/'cache.json') if (out/'cache.json').exists() else {}
   def execute(name,min_modes=0,rerun=False):
    index=STAGES.index(name);pre=cache.get(STAGES[index-1],{}).get('artifacts') if index else None
    key=fingerprint({'base':base,'stage':name,'prerequisite':pre})
    target=out/name;entry=cache.get(name,{})
    if not force and not rerun and target.exists() and entry.get('key')==key and entry.get('artifacts')==files(target):
     status['stages'][name]={'status':'cached'};print(f'{name}: verified cache',flush=True);return
    if target.exists():shutil.rmtree(target)
    target.mkdir();t=time.monotonic();kind=selected if name in ('modal','psd') else 'cpu'
    python='/opt/psd-python/bin/python' if name=='psd' and selected=='cuda' else '/usr/bin/python3'
    command=[python,'-m','pcb_mechanical.worker',name,'/work/case.json','/work','--backend',selected,'--min-modes',str(min_modes)]
    measured=['/usr/bin/python3','-m','pcb_mechanical.measure',f'/work/{name}/resources.json','--max-rss-gib',str(c['execution']['max_memory_gib']),'--min-available-gib',str(c['execution']['host_reserve_gib'])]+(['--max-gpu-gib',str(c['execution']['gpu_memory_gib'])] if selected=='cuda' and name in ('modal','psd') else [])+['--']+command
    rt.run(kind,measured,output=out,gpu_count=int(kind=='cuda'),memory_gib=c['execution']['max_memory_gib'],env={'OMP_NUM_THREADS':str(c['execution']['threads']),'OPENBLAS_NUM_THREADS':str(c['execution']['threads'])},log=out/f'{name}.log')
    cache[name]={'key':key,'artifacts':files(target)};write_json(out/'cache.json',cache)
    status['stages'][name]={'status':'completed','wall_seconds':time.monotonic()-t};write_json(out/'run.json',status)
   end=len(STAGES)-1 if stage=='all' else STAGES.index(stage)
   if c['analysis']=='modal' and stage=='all':end=STAGES.index('modal')
   for name in STAGES[:end+1]:
    execute(name)
    if name=='psd':
     while read_config(out/'psd/psd-summary.json')['status']=='insufficient_modes':
      current=read_config(out/'modal/modal-summary.json')['mode_count']
      larger=[n for n in c['modal']['batches'] if n>current]
      if not larger:break
      print(f'PSD truncation needs more modes: {current} -> {larger[0]}',flush=True)
      execute('modal',min_modes=larger[0],rerun=True);execute('psd',rerun=True)
   if digest(out/'input/board.kicad_pcb')!=source:raise WorkflowError('Input snapshot changed during execution')
   if implementation()!=base['implementation']:raise WorkflowError('Workflow implementation changed during execution; rerun')
   status['status']='complete'
   if end>=STAGES.index('psd') and read_config(out/'psd/psd-summary.json')['status']!='complete':status['status']='insufficient_modes'
 except BaseException as error:
  status.update(status='incomplete',error=str(error),error_type=type(error).__name__)
  raise
 finally:
  if status['status']=='incomplete':rt.stop_batch(owner)
  if old_owner is None:os.environ.pop('PCB_MECHANICAL_BATCH_ID',None)
  else:os.environ['PCB_MECHANICAL_BATCH_ID']=old_owner
  status['wall_seconds']=time.monotonic()-start;write_json(out/'run.json',status)
 return out,status
