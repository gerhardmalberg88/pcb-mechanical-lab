import json,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
from pcb_mechanical.common import WorkflowError,digest
from pcb_mechanical.pipeline import prepare,files,deadline
from pcb_mechanical.config import DEFAULTS,merge,validate

class Workflow(unittest.TestCase):
 def test_snapshot_does_not_write_source(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source';source.mkdir();p=source/'board.kicad_pcb';p.write_text('saved board');(source/'LICENSE').write_text('hardware license')
   before=files(source);c=merge(DEFAULTS,{'board':str(p),'output':str(root/'results')})
   out,sha,frozen=prepare(c)
   self.assertEqual(files(source),before);self.assertEqual(digest(out/'input/board.kicad_pcb'),digest(p))
   self.assertEqual((out/'input/LICENSE').read_text(),'hardware license')
 def test_source_git_tree_is_never_an_output(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'.git').mkdir();(root/'.git/HEAD').write_text('ref: refs/heads/main')
   board=root/'board';board.write_text('board')
   with self.assertRaises(WorkflowError):prepare(merge(DEFAULTS,{'board':str(board),'output':str(root/'sim')}))
   self.assertFalse((root/'sim').exists())
 def test_solver_nonconvergence_is_rejected(self):
  from pcb_mechanical.worker import verify_log
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'solver.log'
   for text in ('FATAL:: AMGX failed to converge\nALL DONE','solver stopped unexpectedly'):
    p.write_text(text)
    with self.assertRaises(WorkflowError):verify_log(p)
 def test_keyboard_interrupt_restores_deadline(self):
  import signal
  previous=signal.getsignal(signal.SIGALRM)
  with self.assertRaises(KeyboardInterrupt):
   with deadline(30):raise KeyboardInterrupt()
  self.assertEqual(signal.getsignal(signal.SIGALRM),previous)
  self.assertEqual(signal.getitimer(signal.ITIMER_REAL)[0],0.)
 def test_insufficient_frequency_coverage_is_rejected(self):
  import numpy as np
  from pcb_mechanical.worker import work
  from pcb_mechanical.common import write_json
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'convert/mesh').mkdir(parents=True);(root/'modal').mkdir()
   write_json(root/'convert/mesh/physical.json',{'bodies':{}});write_json(root/'case.json',DEFAULTS)
   def solver(*args,**kw):Path(kw['log']).write_text('ALL DONE')
   with patch('pcb_mechanical.worker.call',side_effect=solver),patch('pcb_mechanical.fem.read_variable',return_value=(np.array([(2*np.pi*100)**2]),None,None,None)):
    with self.assertRaisesRegex(WorkflowError,'did not cover'):work('modal',root/'case.json',root,'cpu')
 def test_gui_edits_are_isolated(self):
  from pcb_mechanical.gui import working_copy
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source';source.mkdir();(source/'case.sif').write_text('authoritative')
   with patch('pcb_mechanical.gui.ROOT',root):out=working_copy(source,'elmer')
   (out/'case.sif').write_text('GUI edit')
   self.assertEqual((source/'case.sif').read_text(),'authoritative')
 def test_runtime_uses_resolved_image_identity(self):
  from pcb_mechanical.runtime import Runtime
  import subprocess
  r=Runtime();r.pinned_images={'cpu':'sha256:immutable'}
  with patch('pcb_mechanical.runtime.call',return_value=subprocess.CompletedProcess([],0)) as invoke:
   r.run('cpu',['ElmerSolver','case.sif'])
  self.assertEqual(invoke.call_args.args[0][-3:],[r.pinned_images['cpu'],'ElmerSolver','case.sif'])
 def test_cache_detects_artifact_change(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a';p.write_text('first');a=files(Path(d));p.write_text('second');self.assertNotEqual(a,files(Path(d)))
 def test_unowned_output_refused(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/'board').write_text('x');out=r/'existing';out.mkdir();(out/'mine').write_text('keep')
   with self.assertRaises(WorkflowError):prepare(merge(DEFAULTS,{'board':str(r/'board'),'output':str(out)}))
   self.assertEqual((out/'mine').read_text(),'keep')
 def test_output_cannot_enclose_board(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'board';p.write_text('x')
   with self.assertRaises(WorkflowError):prepare(merge(DEFAULTS,{'board':str(p),'output':d}))
 def test_deadline_interrupts(self):
  with self.assertRaises(WorkflowError):
   with deadline(.02):time.sleep(.1)
 def test_nested_deadline_preserves_outer(self):
  with self.assertRaises(WorkflowError):
   with deadline(.04):
    with deadline(10):time.sleep(.1)
 def test_invalid_density_rejected(self):
  c=merge(DEFAULTS,{'material':{'density_kg_m3':0}})
  with self.assertRaises(WorkflowError):validate(c)
if __name__=='__main__':unittest.main()

class ResourceGuard(unittest.TestCase):
 def test_memory_guard_stops_only_its_child(self):
  import subprocess,sys
  with tempfile.TemporaryDirectory() as d:
   other=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'])
   try:
    result=subprocess.run([sys.executable,'-m','pcb_mechanical.measure',str(Path(d)/'resources.json'),'--max-rss-gib','0.001','--min-available-gib','0','--min-disk-gib','0','--',sys.executable,'-c','import time; data=bytearray(8*1024*1024); time.sleep(20)'],capture_output=True,text=True,timeout=10)
    self.assertNotEqual(result.returncode,0);self.assertIsNone(other.poll())
    self.assertEqual(json.loads((Path(d)/'resources.json').read_text())['stop_reason'],'process_tree_rss_limit')
   finally:other.terminate();other.wait()
