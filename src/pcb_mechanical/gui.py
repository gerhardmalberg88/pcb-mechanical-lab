"""GUI launch on editable copies, preserving authoritative numerical artifacts."""
from pathlib import Path
import shutil,tempfile
from .common import ROOT,write_json,WorkflowError
from .runtime import Runtime

def working_copy(source,tool):
 source=Path(source).resolve()
 if not source.is_dir():raise WorkflowError(f'GUI source directory does not exist: {source}')
 parent=ROOT/'results/gui';parent.mkdir(parents=True,exist_ok=True)
 if source==parent or source in parent.parents:raise WorkflowError('GUI source cannot contain the GUI output directory')
 dest=Path(tempfile.mkdtemp(prefix=tool+'-',dir=parent))
 shutil.copytree(source,dest,dirs_exist_ok=True,symlinks=False)
 write_json(dest/'gui-copy.json',{'source':str(source),'tool':tool,'policy':'Editable copy; authoritative artifacts remain unchanged'})
 return dest

def launch(tool,source,args,seconds=None):
 dest=working_copy(source,tool);print(f'GUI working copy: {dest}',flush=True)
 defaults={'gmsh':['/work/board.msh'],'paraview':['--data=/work/rms.vtu']}
 command=[tool]+(args or defaults.get(tool,[]))
 if seconds:command=['timeout','--signal=TERM','--kill-after=3',str(seconds)]+command
 result=Runtime().run('tools',command,output=dest,gui=True,check=False,log=dest/'gui.log')
 success=result.returncode==0 or bool(seconds and result.returncode==124)
 write_json(dest/'gui-launch.json',{'tool':tool,'command':command,'exit_code':result.returncode,'launched_for_smoke_test':success and bool(seconds),'note':'Window lifetime alone does not prove project contents loaded'})
 if not success:raise WorkflowError(f'GUI exited with {result.returncode}; see {dest}/gui.log')
 return 0
