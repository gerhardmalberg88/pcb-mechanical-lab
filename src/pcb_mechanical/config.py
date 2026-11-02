"""JSON case interface and physical defaults. Internal FEM quantities are SI."""
from copy import deepcopy
from pathlib import Path
import math
from .common import read_config,WorkflowError
DEFAULTS={
 'schema':1,'name':'PCB mechanical screening','analysis':'all',
 'material':{'young_pa':24.37e9,'poisson':0.165,'density_kg_m3':1944.,'provenance':'Generic effective PCB; https://ansyshelp.ansys.com/public/Views/Secured/corp/v251/en/discovery_tech_show/Discovery/tech_show/nat_freq_analy_prnt_circ_board/c_nat_freq_mat_props.html'},
 'mounts':{'kind':None,'refs':[],'outer_diameter_mm':None},
 'components':{'enabled':True,'mass_overrides_g':{}},
 'mesh':{'size_mm':3.,'mount_size_mm':0.9,'layers':2,'max_dofs':150000},
 'modal':{'batches':[16,32,64,128],'minimum_frequency_hz':3000.,'residual_tolerance':1e-6,'orthogonality_tolerance':1e-6},
 'psd':{'frequency_hz':[20.,2000.],'density_g2_hz':[1/1980,1/1980],'damping':0.02,'sensitivity_damping':[0.01,0.05],'integration_tolerance':0.01,'truncation_tolerance':0.05},
 'execution':{'backend':'cpu','threads':2,'max_memory_gib':6.,'host_reserve_gib':2.,'gpu_memory_gib':4.5,'time_budget_minutes':60.},
}
def merge(base,update):
 out=deepcopy(base)
 for k,v in update.items():out[k]=merge(out[k],v) if isinstance(v,dict) and isinstance(out.get(k),dict) else v
 return out

def validate(c):
 if c['schema']!=1:raise WorkflowError('Unsupported case schema')
 if c['analysis'] not in ('modal','psd','all'):raise WorkflowError('analysis must be modal, psd or all')
 m=c['material']
 for key in ('young_pa','density_kg_m3'):
  if not math.isfinite(m[key]) or m[key]<=0:raise WorkflowError(f'Invalid {key}')
 if not -1<m['poisson']<.5:raise WorkflowError('Poisson ratio must lie between -1 and 0.5')
 for key in ('size_mm','mount_size_mm','max_dofs'):
  if not math.isfinite(c['mesh'][key]) or c['mesh'][key]<=0:raise WorkflowError('Invalid mesh size/limit')
 if not isinstance(c['mesh']['layers'],int) or c['mesh']['layers']<2:raise WorkflowError('At least two elements through thickness are required')
 p=c['psd'];f=p['frequency_hz'];s=p['density_g2_hz']
 if len(f)!=len(s) or len(f)<2 or any(not math.isfinite(x) for x in f+s) or f[0]<=0 or any(b<=a for a,b in zip(f,f[1:])) or min(s)<0:raise WorkflowError('PSD requires increasing positive Hz and nonnegative g²/Hz')
 if not 0<p['damping']<1 or any(not 0<x<1 for x in p['sensitivity_damping']):raise WorkflowError('Damping ratios must lie between zero and one')
 mounts=c['mounts']
 if mounts['kind'] not in ('holes','cantilever'):raise WorkflowError('Case must explicitly select mounts.kind: holes or cantilever')
 if mounts['kind']=='holes':
  refs=mounts['refs'];diameter=mounts['outer_diameter_mm']
  if not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or not ref.strip() for ref in refs) or len(set(refs))!=len(refs):raise WorkflowError('Hole mounts require explicit, unique footprint references')
  if not isinstance(diameter,(int,float)) or not math.isfinite(diameter) or diameter<=0:raise WorkflowError('Hole mounts require an explicit positive contact diameter in mm')
 elif mounts['refs']:raise WorkflowError('Cantilever mounts do not take hole references')
 if c['execution']['backend'] not in ('cpu','cuda','auto'):raise WorkflowError('Unknown backend')
 if not 1<c['execution']['time_budget_minutes']<=60:raise WorkflowError('Time budget must exceed one minute and not exceed 60 minutes')
 for key in ('max_memory_gib','gpu_memory_gib','host_reserve_gib'):
  if not math.isfinite(c['execution'][key]) or c['execution'][key]<=0:raise WorkflowError(f'Invalid resource limit {key}')
 if not isinstance(c['execution']['threads'],int) or c['execution']['threads']<1:raise WorkflowError('threads must be a positive integer')
 for key in ('integration_tolerance','truncation_tolerance'):
  if not 0<p[key]<1:raise WorkflowError(f'Invalid PSD {key}')
 if c['modal']['minimum_frequency_hz']<max(p['frequency_hz']):raise WorkflowError('Modal coverage must include the complete excitation band')
 batches=c['modal']['batches']
 if not batches or sorted(set(batches))!=batches or any(not isinstance(n,int) or n<1 for n in batches):raise WorkflowError('Modal batches must be increasing positive integers')
 return c

def load(path):
 path=Path(path).resolve();c=validate(merge(DEFAULTS,read_config(path)))
 c['board']=str((path.parent/c['board']).resolve())
 c['output']=str((path.parent/c.get('output','results')).resolve())
 c['case_file']=str(path)
 return c
