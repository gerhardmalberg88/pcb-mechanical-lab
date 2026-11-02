"""Container-side stages; all writable paths belong to /work."""
from pathlib import Path
import argparse,json,shutil,time
from .common import read_config,write_json,call,WorkflowError

def verify_log(path):
 text=Path(path).read_text().lower()
 if any(word in text for word in ('error::','fatal::','failed to converge','did not converge','segmentation fault')) or 'all done' not in text:
  raise WorkflowError(f'Elmer did not complete cleanly: {path}')

def work(stage,case,root,backend,min_modes=0):
 root=Path(root);c=read_config(case)
 if stage=='extract':
  from .extract import extract
  extract(root/'input/board.kicad_pcb',root/'extract/board.json',c)
 elif stage=='mesh':
  from .mesh import generate
  generate(read_config(root/'extract/board.json'),c,root/'mesh')
 elif stage=='convert':
  from .fem import distribute_masses
  call(['ElmerGrid','14','2',root/'mesh/board.msh','-out',root/'convert/mesh'])
  distribute_masses(root/'convert/mesh',read_config(root/'extract/board.json'),c)
 elif stage=='modal':
  import numpy as np
  from .solver import generate
  from .fem import read_variable,analyze
  out=root/'modal';shutil.copytree(root/'convert/mesh',out/'mesh',dirs_exist_ok=True)
  physical=read_config(out/'mesh/physical.json')
  counts=[n for n in c['modal']['batches'] if n>=min_modes]
  for count in counts:
   generate(c,physical,out,backend,count,raw=not (out/'raw_a.dat').exists())
   call(['ElmerSolver','case.sif'],cwd=out,log=out/f'elmer-{count}.log')
   verify_log(out/f'elmer-{count}.log')
   eig=read_variable(out/'modes.bin')[0]
   if np.sqrt(eig[-1])/(2*np.pi)>=c['modal']['minimum_frequency_hz']:break
  else:raise WorkflowError('Maximum mode count did not cover the required frequency band')
  summary=analyze(out,c,physical);summary['backend']=backend;summary['amgx_dispatch']=backend=='cuda'
  write_json(out/'modal-summary.json',summary)
  data=np.load(out/'modal.npz');res=out/'residual';res.mkdir(exist_ok=True)
  shutil.copytree(out/'mesh',res/'mesh',dirs_exist_ok=True)
  values=data['residual_shape']
  with (res/'prescribed.bin').open('wb') as stream:
   np.array([values.shape[0],3],dtype='<i4').tofile(stream);np.asarray(values,dtype='<f8').tofile(stream)
  generate(c,physical,res,'cpu',3,raw=False,prescribed=True)
  call(['ElmerSolver','case.sif'],cwd=res,log=res/'elmer.log')
  verify_log(res/'elmer.log')
 elif stage=='psd':
  from .psd import run
  run(root/'modal',c,root/'psd',backend)
 elif stage=='postprocess':
  from .postprocess import render
  render(c,root)
 else:raise WorkflowError(f'Unknown stage {stage}')

def main():
 p=argparse.ArgumentParser();p.add_argument('stage');p.add_argument('case');p.add_argument('root');p.add_argument('--backend',default='cpu');p.add_argument('--min-modes',type=int,default=0)
 a=p.parse_args();work(a.stage,a.case,a.root,a.backend,a.min_modes)
if __name__=='__main__':main()
