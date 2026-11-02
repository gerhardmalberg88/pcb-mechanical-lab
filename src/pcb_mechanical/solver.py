"""Generate authoritative Elmer SIFs for consistent-mass modal analysis."""
import json
from pathlib import Path
from .common import write_json

def amgx_configuration():
    # The plate's ill-conditioned bending operator stalled with scalar AMG.
    # AMGX PCG with diagonal preconditioning converged without changing physics.
    return {'config_version':2,'solver':{
        'scope':'main','solver':'PCG','print_solve_stats':0,'obtain_timings':1,
        'max_iters':20000,'monitor_residual':1,'convergence':'RELATIVE_INI',
        'tolerance':1e-11,'norm':'L2',
        'preconditioner':{'solver':'BLOCK_JACOBI','max_iters':1,'relaxation_factor':1.}}}


def generate(case,physical,out,backend,count,raw=True,prescribed=False):
 out=Path(out);m=case['material']
 linear='Linear System Solver = Direct\n  Linear System Direct Method = Cholmod' if backend=='cpu' else 'Linear System Solver = amgx\n  AMGX Config = String "amgx.json"'
 text=f'''! PCB Mechanical Lab. SI units. Generic effective board material.
Check Keywords Warn
Header
  Mesh DB "." "mesh"
End
Simulation
  Coordinate System = Cartesian 3D
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Max Output Level = 5
End
Equation 1
  Active Solvers(2) = 1 2
End
Solver 1
  Equation = Stress Analysis
  Procedure = "MechanicalStress" "StressSolver"
  Variable = Displacement
  Variable Dofs = 3
  Eigen Analysis = Logical True
  Eigen System Values = {count}
  Eigen System Select = Smallest Magnitude
  Eigen System Shift = 0.0
  Eigen System Max Iterations = 1000
  Eigen System Convergence Tolerance = 1e-9
  Eigen System Normalize To Unity = Logical False
  Linear System Symmetric = Logical True
  Linear System Scaling = Logical {'True' if backend=='cuda' else 'False'}
  Linear System Abort Not Converged = Logical True
  Linear System Convergence Tolerance = 1e-11
  Linear System Max Iterations = 3000
  {linear}
  Calculate Stresses = Logical True
  Calculate Strains = Logical True
  Displace Mesh = Logical False
  Nonlinear System Max Iterations = 1
  Mechanical Export Raw = Logical {'True' if raw else 'False'}
  Mechanical Prescribed Modes = Logical {'True' if prescribed else 'False'}
  Linear System Save Mass = Logical True
  Linear System Save Perm = Logical True
End
Solver 2
  Exec Solver = After Simulation
  Equation = Mechanical Export
  Procedure = "MechanicalExport" "MechanicalExport"
End
Boundary Condition 1
  Target Boundaries(1) = 2
  Displacement 1 = Real 0.0
  Displacement 2 = Real 0.0
  Displacement 3 = Real 0.0
End
'''
 for bid,rho in physical['bodies'].items():
  text+=f'''Body {bid}
  Target Bodies(1) = {bid}
  Equation = 1
  Material = {bid}
End
Material {bid}
  Youngs Modulus = Real {m['young_pa']:.15g}
  Poisson Ratio = Real {m['poisson']:.15g}
  Density = Real {rho:.15g}
End
'''
 (out/'case.sif').write_text(text)
 write_json(out/'amgx.json',amgx_configuration())
 import xml.etree.ElementTree as ET
 root=ET.Element('contents');ET.SubElement(root,'geometryinputfile').text='mesh.header'
 general=ET.SubElement(root,'generalsetup');widget=ET.SubElement(general,'widget',{'type':'LineEdit'})
 ET.SubElement(widget,'objectName').text='solverInputFileEdit';ET.SubElement(widget,'text').text='case.sif'
 for section in ('operations','parallelsettings','meshparameters','solverparameters','equation','material','bodyforce','initialcondition','boundarycondition','bodyproperties','boundaryproperties','solverspecificoptions'):ET.SubElement(root,section)
 gui=out/'mesh'
 if gui.exists():
  ET.ElementTree(root).write(gui/'egproject.xml',encoding='UTF-8',xml_declaration=True)
  (gui/'case.sif').write_text(text.replace('Mesh DB "." "mesh"','Mesh DB "." "."'))
  (gui/'ELMERSOLVER_STARTINFO').write_text('case.sif\n1\n')
  write_json(gui/'amgx.json',amgx_configuration())
 return out/'case.sif' 
