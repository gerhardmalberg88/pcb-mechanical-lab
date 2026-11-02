"""Public PCB Mechanical Lab commands."""
import argparse,os,sys
from pathlib import Path
from .common import ROOT,WorkflowError,call,positive

def parser():
 p=argparse.ArgumentParser(prog='pcb-mechanical',description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 b=sub.add_parser('bootstrap');b.add_argument('--cuda',action='store_true')
 b=sub.add_parser('build');b.add_argument('--profile',choices=['cpu','tools','cuda','all'],default='cpu');b.add_argument('--jobs',type=positive,default=2);b.add_argument('--cuda-arch',default='75');b.add_argument('--cuda-version',default='12.9.1');b.add_argument('--reuse-installed',action='store_true')
 b=sub.add_parser('doctor');b.add_argument('--backend',choices=['cpu','cuda','auto'],default='cpu');b.add_argument('--full',action='store_true')
 b=sub.add_parser('run');b.add_argument('case',type=Path);b.add_argument('--stage',choices=['extract','mesh','convert','modal','psd','postprocess','all'],default='all');b.add_argument('--backend',choices=['cpu','cuda','auto']);b.add_argument('--force',action='store_true');b.add_argument('--time-budget-minutes',type=float)
 b=sub.add_parser('study');b.add_argument('--case',type=Path,required=True,help='JSON case defining the board, mounting and physical model');b.add_argument('--board',type=Path,help='Override the case board path');b.add_argument('--backend',choices=['cpu','cuda'],default='cpu');b.add_argument('--time-budget-minutes',type=float,default=60);b.add_argument('--output',type=Path)
 b=sub.add_parser('gui');b.add_argument('tool',choices=['gmsh','elmer','paraview','freecad','kicad','pcbnew']);b.add_argument('--workdir',type=Path,required=True);b.add_argument('args',nargs='*');b.add_argument('--smoke-test-seconds',type=positive)
 for name in ['export','import']:
  b=sub.add_parser(name);b.add_argument('directory',type=Path)
  if name=='export':b.add_argument('--profile',choices=['cpu','cuda','all'],default='cpu')
 return p

def main(argv=None):
 argv=list(sys.argv[1:] if argv is None else argv);extra=[]
 if argv and argv[0]=='gui' and '--' in argv:i=argv.index('--');extra=argv[i+1:];argv=argv[:i]
 a=parser().parse_args(argv)
 try:
  if a.command=='bootstrap':
   call(['bash',ROOT/'scripts/bootstrap-host.sh'])
   if a.cuda:call(['sudo','bash',ROOT/'scripts/bootstrap-nvidia.sh'])
  elif a.command=='build':
   from .build import build
   if a.reuse_installed:
    from .build import reuse_installed
    reuse_installed(a.profile,a.jobs)
   else:build(a.profile,a.jobs,a.cuda_arch,a.cuda_version)
  elif a.command=='run':
   from .pipeline import run
   out,status=run(a.case,a.stage,a.backend,a.force,a.time_budget_minutes);print(out)
   return 0 if status['status']=='complete' else 2
  elif a.command=='study':
   from .study import study
   return study(a.case,a.backend,a.time_budget_minutes,a.output,board=a.board)
  elif a.command=='doctor':
   from .validation import doctor
   return doctor(a.backend,a.full)
  elif a.command=='gui':
   from .runtime import Runtime
   tool={'elmer':'ElmerGUI'}.get(a.tool,a.tool)
   from .gui import launch
   return launch(tool,a.workdir,a.args+extra,a.smoke_test_seconds)
  elif a.command in ('export','import'):
   from .build import transfer
   transfer(a.directory,a.profile if a.command=='export' else None)
  return 0
 except (WorkflowError,OSError,ValueError,KeyError) as e:print(f'pcb-mechanical: {e}',file=sys.stderr);return 1
 except KeyboardInterrupt:print('Interrupted; logs and successful stages retained.',file=sys.stderr);return 130
if __name__=='__main__':raise SystemExit(main())
