import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pcb_mechanical.common import WorkflowError
from pcb_mechanical.config import DEFAULTS, merge, validate, load


class Cases(unittest.TestCase):
 def test_mounting_requires_an_explicit_physical_choice(self):
  with self.assertRaisesRegex(WorkflowError, 'explicitly select'):
   validate(merge(DEFAULTS, {}))
  case=validate(merge(DEFAULTS, {'mounts': {'kind': 'cantilever'}}))
  self.assertEqual(case['mounts']['refs'], [])
  self.assertIsNone(case['mounts']['outer_diameter_mm'])

 def test_hole_mounts_require_references_and_contact_size(self):
  for mounts in ({'kind':'holes'}, {'kind':'holes','refs':['MP1']},
                 {'kind':'holes','refs':['MP1'],'outer_diameter_mm':float('nan')},
                 {'kind':'holes','refs':['MP1','MP1'],'outer_diameter_mm':5}):
   with self.subTest(mounts=mounts), self.assertRaises(WorkflowError):
    validate(merge(DEFAULTS, {'mounts':mounts}))
  mounts={'kind':'holes','refs':['MP1','MP2'],'outer_diameter_mm':5}
  self.assertEqual(validate(merge(DEFAULTS, {'mounts':mounts}))['mounts'], mounts)

 def test_standalone_cases_remain_valid(self):
  root=Path(__file__).resolve().parents[1]
  for filename in ('case.json','case-cuda.json'):
   self.assertEqual(load(root/'examples/cantilever'/filename)['mounts']['kind'], 'cantilever')

 def test_study_preserves_case_and_snapshots_board_override(self):
  from pcb_mechanical.study import study
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'board.kicad_pcb').write_text('original board')
   board=root/'replacement.kicad_pcb';board.write_text('saved replacement')
   case={'name':'Custom plate','board':'board.kicad_pcb','analysis':'modal',
         'material':{'density_kg_m3':1800},
         'mounts':{'kind':'holes','refs':['MP1','MP2'],'outer_diameter_mm':5},
         'components':{'mass_overrides_g':{'U1':0.3}},
         'mesh':{'size_mm':6},'execution':{'max_memory_gib':3}}
   path=root/'case.json';path.write_text(json.dumps(case));seen=[]
   def run(c):
    seen.append(c)
    self.assertEqual(Path(c['board']).read_text(), 'saved replacement')
    board.write_text('later user edit')
    return Path(c['output']), {'status':'complete'}
   def compare(*args, **kwargs):
    self.assertEqual(kwargs['memory_gib'],3)
    (kwargs['output']/'comparison.json').write_text('{"accepted":true}')
   with patch('pcb_mechanical.study.ROOT',root), patch('pcb_mechanical.study.run_case',side_effect=run), patch('pcb_mechanical.study.Runtime') as runtime:
    runtime.return_value.run.side_effect=compare
    self.assertEqual(study.__wrapped__(path,board=board),0)
   self.assertEqual([c['mesh']['size_mm'] for c in seen],[6,4])
   for c in seen:
    self.assertEqual(c['mounts'],case['mounts'])
    self.assertEqual(c['material']['density_kg_m3'],1800)
    self.assertEqual(c['components']['mass_overrides_g'],{'U1':0.3})
    self.assertEqual(c['analysis'],'all')
   out=root/'results/studies/replacement/cpu'
   self.assertEqual(json.loads((out/'study.json').read_text())['status'],'complete')
   self.assertIn('# PCB mechanical screening',(out/'report.md').read_text())
