"""Coherent modal random response: real-field quadratic forms, NumPy or CuPy."""
from pathlib import Path
import json,time
import numpy as np
from .common import WorkflowError,write_json
from .fem import read_variable
G=9.80665

def backend_module(backend,limit=4.5):
 if backend=='cpu':return np,{'backend':'cpu','precision':'float64/complex128'}
 import cupy as cp
 cp.get_default_memory_pool().set_limit(size=int(limit*1024**3))
 cp.cuda.runtime.getDeviceCount();a=cp.arange(16,dtype=cp.float64);float(cp.sum(a*a).get());cp.cuda.Stream.null.synchronize()
 props=cp.cuda.runtime.getDeviceProperties(0)
 return cp,{'backend':'cuda','device':props['name'].decode(),'cupy':cp.__version__,'precision':'float64/complex128','device_execution':True,'memory_limit_gib':limit}

def frequency_grid(freq,p,refinement=1):
 lo,hi=p['frequency_hz'][0],p['frequency_hz'][-1]
 z=min([p['damping']]+p['sensitivity_damping']);points=[np.linspace(lo,hi,2001*refinement),np.asarray(p['frequency_hz'])]
 for f in freq:
  if lo<=f<=hi:
   points.append(f+np.linspace(-8,8,65*refinement)*z*f)
 a=np.unique(np.concatenate(points));return a[(a>=lo)&(a<=hi)]

def weights(f):
 w=np.empty_like(f);w[0]=(f[1]-f[0])/2;w[-1]=(f[-1]-f[-2])/2;w[1:-1]=(f[2:]-f[:-2])/2
 return w

def covariance(freq,gamma,axis,f,p,zeta,xp):
 omega=xp.asarray(2*np.pi*f);wn=xp.asarray(2*np.pi*freq)
 q=-xp.asarray(gamma[:,axis,None])/(wn[:,None]**2-omega[None,:]**2+2j*zeta*wn[:,None]*omega[None,:])
 c=xp.vstack((q,xp.ones((1,len(f))),xp.zeros((1,len(f)))))
 ca=xp.vstack((-q*omega**2,-omega[None,:]**2,xp.ones((1,len(f)))))
 s=np.interp(f,p['frequency_hz'],p['density_g2_hz'])*G**2
 w=xp.asarray(weights(f)*s)
 def cov(v):return xp.real((v*w)@v.conj().T)
 return cov(c),cov(ca),q,s

def rms_field(basis,cov,xp):
 out=np.empty(len(basis))
 for first in range(0,len(basis),1024):
  b=xp.asarray(basis[first:first+1024]);variance=xp.sum((b@cov)*b,axis=1)
  result=xp.sqrt(xp.maximum(variance,0))
  out[first:first+len(b)]=result if xp is np else result.get()
 return out

def evaluate(data,residual_stress,residual_strain,p,f,zeta,xp,keep=None):
 n=len(data['frequencies']) if keep is None else keep;freq=data['frequencies'][:n];gamma=data['gamma'][:n]
 res=data['residual_shape'].copy();rs=residual_stress.copy();re=residual_strain.copy()
 if n<len(data['frequencies']):
  tail=data['gamma'][n:]/data['eigenvalues'][n:,None]
  res-=data['phi'][:,n:]@tail;rs-=data['stress'][:,n:]@tail;re-=data['strain'][:,n:]@tail
 outputs={};spectra={}
 # Probe all displacement components at regular node intervals; full fields use the same covariance.
 probe=np.unique(np.linspace(0,len(data['phi'])-1,min(60,len(data['phi'])),dtype=int))
 for axis in range(3):
  cu,ca,q,s=covariance(freq,gamma,axis,f,p,zeta,xp)
  rigid=np.tile(np.eye(3),(len(data['phi'])//3,1))[:,axis]
  b=np.column_stack((data['phi'][:,:n],res[:,axis],rigid))
  outputs[f'displacement_{axis}']=rms_field(b,cu,xp)
  outputs[f'acceleration_{axis}']=rms_field(b,ca,xp)
  outputs[f'stress_{axis}']=rms_field(np.column_stack((data['stress'][:,:n],rs[:,axis],np.zeros(len(rs)))),cu,xp)
  outputs[f'strain_{axis}']=rms_field(np.column_stack((data['strain'][:,:n],re[:,axis],np.zeros(len(re)))),cu,xp)
  h=xp.asarray(data['phi'][probe,:n])@q+xp.asarray(res[probe,axis,None])
  ha=-h*xp.asarray((2*np.pi*f)**2)+xp.asarray(rigid[probe,None])
  a=xp.abs(ha)**2*xp.asarray(s)
  spectra[str(axis)]=np.asarray(a) if xp is np else a.get()
 return outputs,spectra,probe

def relative_change(a,b):
 changes={}
 for key in a:
  floor=max(float(np.max(np.abs(a[key])))*1e-3,1e-20)
  changes[key]=float(np.max(np.abs(a[key]-b[key])/np.maximum(np.abs(a[key]),floor)))
 return changes

def run(modal_dir,case,out,backend):
 started=time.monotonic();out=Path(out);out.mkdir(parents=True,exist_ok=True);m=Path(modal_dir)
 data=dict(np.load(m/'modal.npz'));rs=read_variable(m/'residual/stress.bin')[1];re=read_variable(m/'residual/strain.bin')[1]
 xp,execution=backend_module(backend,case['execution']['gpu_memory_gib']);p=case['psd'];previous=None;converged=False
 for refinement in (1,2,4,8):
  f=frequency_grid(data['frequencies'],p,refinement)
  outputs,spectra,probe=evaluate(data,rs,re,p,f,p['damping'],xp)
  integration=relative_change(outputs,previous) if previous is not None else None
  if integration and max(integration.values())<p['integration_tolerance']:converged=True;break
  previous=outputs
 if not converged:raise WorkflowError('PSD frequency integration did not converge')
 keep=max(1,int(len(data['frequencies'])*.75));reduced,_,_=evaluate(data,rs,re,p,f,p['damping'],xp,keep)
 truncation=relative_change(outputs,reduced)
 sensitivities={}
 for z in p['sensitivity_damping']:
  fields,_,_=evaluate(data,rs,re,p,f,z,xp)
  sensitivities[str(z)]={k:float(v.max()) for k,v in fields.items()}
 np.savez_compressed(out/'rms.npz',**outputs)
 np.savez_compressed(out/'probe-psd.npz',frequencies=f,probe_dofs=probe,**{f'axis_{k}':v for k,v in spectra.items()})
 input_rms=float(np.sqrt(np.trapz(np.interp(f,p['frequency_hz'],p['density_g2_hz']),f)))
 if xp is not np:xp.cuda.Stream.null.synchronize();execution['allocated_bytes']=xp.get_default_memory_pool().total_bytes()
 summary={'status':'complete' if max(truncation.values())<p['truncation_tolerance'] else 'insufficient_modes','execution':execution,'wall_seconds':time.monotonic()-started,'input_rms_g':input_rms,'damping_ratio':p['damping'],'frequency_points':len(f),'integration_relative_change':integration,'truncation_relative_change':truncation,'truncation_modes':keep,'retained_modes':len(data['frequencies']),'maxima':{k:float(v.max()) for k,v in outputs.items()},'damping_sensitivity_maxima':sensitivities,'residual_flexibility':'included in displacement, absolute acceleration, stress and strain','axes':'Separate X/Y/Z excitation; not combined','stress_components':'Elmer tensor components; RMS von Mises is not inferred'}
 write_json(out/'psd-summary.json',summary)
 for axis in range(3):np.savetxt(out/f'probe-psd-{axis}.csv',np.column_stack((f,spectra[str(axis)].T)),delimiter=',',header='frequency_hz,'+','.join(f'absolute_acceleration_psd_dof_{n}_m2_s4_hz' for n in probe),comments='')
 return summary
