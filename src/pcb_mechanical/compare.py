"""Physical probe mesh comparison and mass-weighted backend mode comparison."""
from pathlib import Path
import argparse
import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import cKDTree
from scipy.optimize import linear_sum_assignment
from scipy import sparse
from .common import read_config,write_json,digest
from .fem import read_mesh
from .postprocess import nodal

def compare(coarse,fine,destination):
 coarse=Path(coarse);fine=Path(fine);a=np.load(coarse/'modal/modal.npz');b=np.load(fine/'modal/modal.npz')
 fa=a['frequencies'];fb=b['frequencies'];n=min(10,len(fa),len(fb));freq=np.abs(fa[:n]-fb[:n])/fb[:n]
 pa,_,_=read_mesh(coarse/'convert/mesh');pb,_,_=read_mesh(fine/'convert/mesh')
 lo=np.minimum(pa.min(axis=0),pb.min(axis=0));hi=np.maximum(pa.max(axis=0),pb.max(axis=0))
 probes=np.array([[lo[0]+x*(hi[0]-lo[0]),lo[1]+y*(hi[1]-lo[1])] for x in (.2,.4,.6,.8) for y in (.25,.5,.75)])
 inputs=read_config(fine/'extract/board.json');case=read_config(fine/'case.json')
 for h in inputs['mounting_holes']:
  if case['mounts']['kind']!='holes' or h['ref'] not in case['mounts']['refs']:continue
  probes=probes[np.linalg.norm(probes-np.array(h['center_mm'])*.001,axis=1)>case['mounts']['outer_diameter_mm']*.001]
 fields_a=np.load(coarse/'psd/rms.npz');fields_b=np.load(fine/'psd/rms.npz');changes={};values={}
 for key in fields_a.files:
  typ=key.split('_')[0];d=3 if typ in ('displacement','acceleration') else 6;pkey='perm' if d==3 else typ+'_perm'
  def sample(points,data,values):
   top=np.isclose(points[:,2],points[:,2].max(),atol=1e-9)
   return LinearNDInterpolator(points[top,:2],nodal(values,data[pkey],d)[top])(probes)
  va=sample(pa,a,fields_a[key]);vb=sample(pb,b,fields_b[key]);valid=np.isfinite(va)&np.isfinite(vb)
  floor=max(float(np.nanmax(np.abs(vb)))*.01,1e-20)
  changes[key]=float(np.max(np.abs(va[valid]-vb[valid])/np.maximum(np.abs(vb[valid]),floor))) if valid.any() else float('inf')
  values[key]={'coarse':va.tolist(),'fine':vb.tolist()}
 result={'accepted':max(freq)<.02 and max(changes.values())<.05,'frequency_relative_changes':freq.tolist(),'maximum_frequency_change':float(max(freq)),'rms_relative_changes':changes,'maximum_rms_change':max(changes.values()),'probe_xy_m':probes.tolist(),'probe_rms':values,'criteria':{'first_ten_frequencies':.02,'representative_rms':.05}}
 write_json(destination,result);return result

def compare_backends(cpu,cuda,destination):
 cpu=Path(cpu);cuda=Path(cuda);a=np.load(cpu/'modal/modal.npz');b=np.load(cuda/'modal/modal.npz')
 if digest(cpu/'mesh/board.msh')!=digest(cuda/'mesh/board.msh'):raise ValueError('Backend comparison requires identical mesh artifacts')
 M=sparse.load_npz(cpu/'modal/mass.npz');cross=a['phi'].T@(M@b['phi']);rows,cols=linear_sum_assignment(-abs(cross)**2)
 freq=np.abs(a['frequencies'][rows]-b['frequencies'][cols])/a['frequencies'][rows]
 # Near-degenerate modes may rotate; singular values compare their invariant subspace.
 groups=[];current=[0]
 for i in range(1,len(rows)):
  if abs(a['frequencies'][i]/a['frequencies'][i-1]-1)<.001:current.append(i)
  else:groups.append(current);current=[i]
 groups.append(current)
 subspaces=[float(np.min(np.linalg.svd(cross[np.ix_(g,cols[g])],compute_uv=False))) for g in groups]
 r1=np.load(cpu/'psd/rms.npz');r2=np.load(cuda/'psd/rms.npz');changes={}
 for key in r1.files:
  floor=max(float(r1[key].max())*1e-3,1e-20)
  changes[key]=float(np.max(abs(r1[key]-r2[key])/np.maximum(abs(r1[key]),floor)))
 result={'accepted':max(freq)<.001 and max(changes.values())<.01 and min(subspaces)>.99,'maximum_frequency_relative_difference':float(max(freq)),'minimum_subspace_overlap':min(subspaces),'rms_relative_differences':changes,'mesh_sha256':digest(cpu/'mesh/board.msh'),'cpu_mode_count':len(a['frequencies']),'cuda_mode_count':len(b['frequencies'])}
 write_json(destination,result);return result

def main():
 p=argparse.ArgumentParser();p.add_argument('first');p.add_argument('second');p.add_argument('output');p.add_argument('--backends',action='store_true');a=p.parse_args()
 (compare_backends if a.backends else compare)(a.first,a.second,a.output)
if __name__=='__main__':main()
