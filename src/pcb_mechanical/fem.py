"""Native Elmer mesh, exact assembled matrices, and modal data interchange."""
from pathlib import Path
import json
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu
from .common import write_json,WorkflowError

def read_mesh(path):
 path=Path(path);rows=np.loadtxt(path/'mesh.nodes');ids=rows[:,0].astype(int)
 if not np.array_equal(ids,np.arange(1,len(ids)+1)):raise WorkflowError('Expected contiguous Elmer node IDs')
 points=rows[:,2:5];elements=[list(map(int,l.split())) for l in (path/'mesh.elements').read_text().splitlines()]
 boundaries=[list(map(int,l.split())) for l in (path/'mesh.boundary').read_text().splitlines()]
 return points,elements,boundaries

def distribute_masses(path,extracted,case):
 path=Path(path);points,elements,boundaries=read_mesh(path)
 centers=[];volumes=[]
 for e in elements:
  p=points[np.array(e[3:])-1];kind=e[2]//100
  if kind==7:
   area=np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0]))/2;v=area*abs(np.mean(p[3:6,2])-np.mean(p[:3,2]))
   center=p[:6].mean(axis=0)
  elif kind==5:
   v=abs(np.linalg.det((p[1:4]-p[0]).T))/6;center=p[:4].mean(axis=0)
  else:raise WorkflowError(f'Unsupported volume element {e[2]}')
  if v<=0:raise WorkflowError('Degenerate volume element')
  centers.append(center);volumes.append(v)
 centers=np.array(centers);volumes=np.array(volumes);rho=np.full(len(elements),case['material']['density_kg_m3']);audit=[]
 for p in extracted['components']:
  x0,y0,x1,y1=np.array(p['box_mm'])*.001
  selected=(centers[:,0]>=x0)&(centers[:,0]<=x1)&(centers[:,1]>=y0)&(centers[:,1]<=y1)
  expanded=False
  if not selected.any():
   distance=(centers[:,0]-(x0+x1)/2)**2+(centers[:,1]-(y0+y1)/2)**2
   selected=np.isclose(distance,distance.min(),rtol=1e-5,atol=1e-16);expanded=True
  rho[selected]+=p['mass_g']*.001/volumes[selected].sum()
  audit.append({**p,'represented_mass_g':p['mass_g'],'attachment_expanded_to_nearest_elements':expanded,'attachment_elements':int(selected.sum())})
 # Binning limits SIF size; volume-weighted means preserve total assigned mass.
 levels=np.unique(rho)
 if len(levels)>64:
  edges=np.quantile(rho,np.linspace(0,1,65));bins=np.digitize(rho,edges[1:-1])
 else:bins=np.searchsorted(levels,rho)
 bodies={};mapping={}
 for b in np.unique(bins):
  sel=bins==b;bid=len(bodies)+1;mapping[int(b)]=bid
  bodies[bid]=float(np.dot(rho[sel],volumes[sel])/volumes[sel].sum())
 for e,b in zip(elements,bins):e[1]=mapping[int(b)]
 (path/'mesh.elements').write_text(''.join(' '.join(map(str,e))+'\n' for e in elements))
 (path/'mesh.names').write_text('$ fixed = 2\n$ free = 3\n'+''.join(f'$ material_{i} = {i}\n' for i in bodies))
 fixed=sorted({node for b in boundaries if b[1]==2 for node in b[5:]})
 if not fixed:raise WorkflowError('Converted mesh has no constrained nodes')
 data={'bodies':bodies,'fixed_nodes':fixed,'board_volume_m3_linear_geometry':float(volumes.sum()),'base_mass_g':float(volumes.sum()*case['material']['density_kg_m3']*1000),'component_mass_g':sum(p['mass_g'] for p in extracted['components']),'components':audit,'density_binning_mass_g':float(np.dot(rho,volumes)*1000)}
 write_json(path/'physical.json',data);return data

def read_variable(path):
 with open(path,'rb') as f:
  n,k,p,d=np.fromfile(f,dtype='<i4',count=4);perm=np.fromfile(f,dtype='<i4',count=p)
  eig=np.fromfile(f,dtype='<f8',count=k);values=np.fromfile(f,dtype='<f8',count=n*k).reshape(n,k)
  if f.read(1):raise WorkflowError('Unexpected modal binary length')
 return eig,values,perm,int(d)

def analyze(directory,case,physical):
 out=Path(directory);eig,phi,perm,d=read_variable(out/'modes.bin')
 if d!=3 or np.any(eig<=0):raise WorkflowError('Nonpositive modes or unexpected displacement DOFs')
 a=np.loadtxt(out/'raw_a.dat');n=int(a[:,:2].max());ij=a[:,:2].astype(np.int64)-1
 K=sparse.coo_matrix((a[:,2],(ij[:,0],ij[:,1])),shape=(n,n)).tocsr()
 M=sparse.coo_matrix((a[:,3],(ij[:,0],ij[:,1])),shape=(n,n)).tocsr();del a,ij
 if phi.shape[0]!=n:raise WorkflowError('Matrix/mode dimensions disagree')
 fixed=np.array([3*(perm[node-1]-1)+j for node in physical['fixed_nodes'] for j in range(3)],int)
 free=np.setdiff1d(np.arange(n),fixed)
 r=np.tile(np.eye(3),(n//3,1));force=M@r
 gram=phi.T@(M@phi);scale=np.sqrt(np.diag(gram));phi=phi/scale
 orth=float(np.max(np.abs(phi.T@(M@phi)-np.eye(len(eig)))))
 kp=(K@phi)[free];mp=(M@phi)[free]*eig
 residual=np.linalg.norm(kp-mp,axis=0)/np.maximum(np.linalg.norm(kp,axis=0)+np.linalg.norm(mp,axis=0),1e-30)
 if max(residual)>case['modal']['residual_tolerance'] or orth>case['modal']['orthogonality_tolerance']:raise WorkflowError(f'Modal accuracy failed: residual={max(residual):.3g}, orthogonality={orth:.3g}')
 gamma=phi.T@force;total=np.diag(r.T@force);participation=np.cumsum(gamma**2,axis=0)/total
 frequency=np.sqrt(eig)/(2*np.pi)
 # Static residual flexibility; retain support-column mass coupling in M @ r.
 lu=splu(K[free][:,free].tocsc());static=np.zeros((n,3));static[free]=lu.solve(-force[free]);del lu
 residual_shape=static+phi@(gamma/eig[:,None])
 stress=read_variable(out/'stress.bin');strain=read_variable(out/'strain.bin')
 arrays={'frequencies':frequency,'eigenvalues':eig,'phi':phi,'gamma':gamma,'perm':perm,'mass_normalization_scale':scale,'residual_shape':residual_shape,'fixed_dofs':fixed,'stress':stress[1]/scale,'stress_perm':stress[2],'strain':strain[1]/scale,'strain_perm':strain[2],'total_mass_kg':total}
 np.savez_compressed(out/'modal.npz',**arrays)
 sparse.save_npz(out/'mass.npz',M);sparse.save_npz(out/'stiffness.npz',K)
 summary={'mode_count':len(eig),'frequencies_hz':frequency.tolist(),'maximum_residual':float(max(residual)),'eigenpair_residuals':residual.tolist(),'mass_orthogonality_error':orth,'effective_mass_fraction_xyz':participation[-1].tolist(),'total_mass_kg_xyz':total.tolist(),'coverage_hz':float(frequency[-1]),'normalization':'phi.T M phi = I','base_force':'-M_full @ rigid_base_direction, including constrained columns'}
 write_json(out/'modal-summary.json',summary)
 np.savetxt(out/'frequencies.csv',np.column_stack([np.arange(1,len(eig)+1),frequency,participation,gamma,scale,residual]),delimiter=',',header='mode,frequency_hz,cumulative_mass_x,cumulative_mass_y,cumulative_mass_z,gamma_x,gamma_y,gamma_z,normalization_scale,eigenpair_residual',comments='')
 return summary
