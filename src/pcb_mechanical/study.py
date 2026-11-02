"""Bounded coarse/refined PCB screening using an explicit physical case."""
from pathlib import Path
import time,json
from .common import ROOT,write_json,read_config,serial_workflow,WorkflowError
from .config import load,merge,validate
from .pipeline import run_case,deadline,prepare,check_output
from .runtime import Runtime

@serial_workflow
def study(case_path,backend='cpu',minutes=60,output=None,*,board=None):
 if not 1<minutes<=60:raise WorkflowError('Study budget must be >1 and <=60 minutes')
 base=load(case_path)
 board=Path(board or base['board']).resolve();root=Path(output or ROOT/'results/studies'/board.stem/backend).resolve();check_output(board,root)
 if root.exists() and any(root.iterdir()) and not (root/'.pcb-mechanical-study').exists():raise WorkflowError('Study output is nonempty and not owned by this workflow')
 root.mkdir(parents=True,exist_ok=True);(root/'.pcb-mechanical-study').touch()
 reserve=min(300.,minutes*60*.1)
 start=time.monotonic();status={'cleanup_reserve_seconds':reserve,'status':'running','backend':backend,'time_budget_minutes':minutes,'source_board':str(board),'variants':{}}
 write_json(root/'study.json',status)
 try:
  with deadline(minutes*60-reserve):
   # Both meshes use the same saved board, even if the hardware checkout changes.
   snapshot,source,_=prepare({'board':str(board),'output':str(root/'snapshot')})
   status['source_sha256']=source;board=snapshot/'input/board.kicad_pcb'
   for variant,size in [('coarse',base['mesh']['size_mm']),('fine',base['mesh']['size_mm']*2/3)]:
    remaining=minutes*60-(time.monotonic()-start)-reserve
    if remaining<=60:raise WorkflowError('Insufficient time for next mesh within study budget')
    case=validate(merge(base,{'name':f"{base['name']} ({variant})",'analysis':'all','board':str(board),'output':str(root/variant),'mesh':{'size_mm':size},'execution':{'backend':backend,'time_budget_minutes':remaining/60}}))
    write_json(root/f'{variant}.json',case)
    out,result=run_case(case);status['variants'][variant]=result;write_json(root/'study.json',status)
   rt=Runtime();rt.run('cpu',['/usr/bin/python3','-m','pcb_mechanical.compare','/work/coarse','/work/fine','/work/comparison.json'],output=root,memory_gib=base['execution']['max_memory_gib'],log=root/'comparison.log')
   comparison=read_config(root/'comparison.json');status['comparison']=comparison
   status['status']='complete' if comparison['accepted'] and all(v['status']=='complete' for v in status['variants'].values()) else 'unconverged'
 except (WorkflowError,OSError,KeyboardInterrupt) as e:
  status.update(status='incomplete',error=str(e))
 finally:
  status['wall_seconds']=time.monotonic()-start;status['under_one_hour']=status['wall_seconds']<3600
  write_json(root/'study.json',status)
  text=f"# PCB mechanical screening\n\nStatus: **{status['status']}**. Backend: **{backend}**. Elapsed: **{status['wall_seconds']/60:.2f} minutes**.\n\n"
  text+='Input and all outputs are external to the hardware checkout. Mounts are assumed rigid; component masses and board material are screening estimates.\n\n'
  for variant in status['variants']:text+=f'- [{variant.capitalize()} report]({variant}/postprocess/report.md)\n'
  if 'comparison' in status:text+='\n```json\n'+json.dumps(status['comparison'],indent=2)+'\n```\n'
  if 'error' in status:text+='\nIncomplete: '+status['error']+'\n'
  (root/'report.md').write_text(text)
 print(root)
 return 0 if status['status']=='complete' and status['under_one_hour'] else 2
