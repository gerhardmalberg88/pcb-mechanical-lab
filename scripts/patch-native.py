#!/usr/bin/env python3
"""Patch the pinned StressSolve to export unscaled matrices before constraints."""
from pathlib import Path
import sys,hashlib,json
root=Path(sys.argv[1]);output=Path(sys.argv[2]);output.mkdir(parents=True,exist_ok=True)
p=root/'fem/src/modules/StressSolve.F90';text=p.read_text()
needle='       CALL DefaultDirichletBCS()'
assert text.count(needle)==1,'Unexpected StressSolve revision'
text=text.replace(needle,'''       IF (GetLogical(SolverParams, 'Mechanical Export Raw', Found)) THEN
         CALL SaveLinearSystem(Solver, LinSysName='raw')
       END IF
'''+needle)
needle='       UNorm = DefaultSolve()'
assert text.count(needle)==1
text=text.replace(needle,'''       IF (GetLogical(SolverParams, 'Mechanical Prescribed Modes', Found)) THEN
         CALL MechanicalReadModes(Solver)
         UNorm = 0.0_dp
       ELSE
         UNorm = DefaultSolve()
       END IF''')
q=output/'MechanicalStress.F90';q.write_text(text)
(output/'patch-native.json').write_text(json.dumps({'upstream':'Elmer 26.1','original':hashlib.sha256(p.read_bytes()).hexdigest(),'patched':hashlib.sha256(q.read_bytes()).hexdigest()},indent=2)+'\n')
