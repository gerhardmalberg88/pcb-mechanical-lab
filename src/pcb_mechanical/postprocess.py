"""Portable VTK fields, mode animations, numerical plots and screening report."""
from pathlib import Path
from xml.sax.saxutils import escape
import json
import numpy as np
from .common import read_config,write_json
from .fem import read_mesh

def nodal(values,perm,dofs):
 a=np.zeros((len(perm),dofs));valid=perm>0;a[valid]=values.reshape(-1,dofs)[perm[valid]-1];return a

def vtu(path,points,elements,fields):
 # Linear display cells use the vertices of quadratic analysis elements.
 cells=[];types=[]
 for e in elements:
  count=6 if e[2]//100==7 else 4;cells.append(np.array(e[3:3+count])-1);types.append(13 if count==6 else 10)
 def array(name,a,kind='Float64'):
  a=np.asarray(a);d=a.shape[1] if a.ndim==2 else 1
  return f'<DataArray type="{kind}" Name="{escape(name)}" NumberOfComponents="{d}" format="ascii">'+ ' '.join(map(str,a.ravel()))+'</DataArray>\n'
 with Path(path).open('w') as f:
  f.write('<?xml version="1.0"?><VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian"><UnstructuredGrid>')
  f.write(f'<Piece NumberOfPoints="{len(points)}" NumberOfCells="{len(cells)}"><Points>');f.write(array('Points',points));f.write('</Points><Cells>')
  f.write(array('connectivity',np.concatenate(cells),'Int32'));f.write(array('offsets',np.cumsum([len(x) for x in cells]),'Int32'));f.write(array('types',types,'UInt8'));f.write('</Cells><PointData>')
  for name,value in fields.items():f.write(array(name,value))
  f.write('</PointData></Piece></UnstructuredGrid></VTKFile>')

def collection(path,names):
 Path(path).write_text('<?xml version="1.0"?><VTKFile type="Collection" version="0.1"><Collection>'+''.join(f'<DataSet timestep="{i}" group="" part="0" file="{name}"/>' for i,name in enumerate(names))+'</Collection></VTKFile>')

def render(case,root):
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 root=Path(root);out=root/'postprocess';out.mkdir(exist_ok=True)
 data=np.load(root/'modal/modal.npz');rms=np.load(root/'psd/rms.npz');modal=read_config(root/'modal/modal-summary.json');psd=read_config(root/'psd/psd-summary.json');physical=read_config(root/'convert/mesh/physical.json')
 points,elements,_=read_mesh(root/'convert/mesh');fields={}
 for axis in range(3):
  for quantity,dofs,perm in [('displacement',3,data['perm']),('acceleration',3,data['perm']),('stress',6,data['stress_perm']),('strain',6,data['strain_perm'])]:
   a=nodal(rms[f'{quantity}_{axis}'],perm,dofs)
   if dofs==3:fields[f'{quantity}_rms_base_{"XYZ"[axis]}']=a
   else:
    for j,label in enumerate(['xx','yy','zz','xy','yz','xz']):fields[f'{quantity}_{label}_rms_base_{"XYZ"[axis]}']=a[:,j]
 vtu(out/'rms.vtu',points,elements,fields)
 names=[]
 for i in range(len(data['frequencies'])):
  name=f'mode-{i+1:03d}.vtu';names.append(name)
  vtu(out/name,points,elements,{'mass_normalized_mode':nodal(data['phi'][:,i],data['perm'],3)})
 collection(out/'modes.pvd',names)
 mode=nodal(data['phi'][:,0],data['perm'],3);factor=np.ptp(points[:,0])*.03/max(np.linalg.norm(mode,axis=1).max(),1e-20)
 animations=[]
 for i in range(12):
  name=f'animation-{i:02d}.vtu';animations.append(name)
  vtu(out/name,points+mode*factor*np.sin(2*np.pi*i/12),elements,{'display_displacement_m':mode*factor*np.sin(2*np.pi*i/12)})
 collection(out/'animation.pvd',animations)
 fig,ax=plt.subplots(figsize=(8,4));ax.plot(np.arange(1,len(data['frequencies'])+1),data['frequencies'],'o-');ax.axhline(case['psd']['frequency_hz'][-1],color='r',label='PSD upper frequency');ax.set(xlabel='Mode',ylabel='Frequency (Hz)',title=case['name']);ax.grid();ax.legend();fig.tight_layout();fig.savefig(out/'frequencies.png');plt.close(fig)
 probe=np.load(root/'psd/probe-psd.npz');fig,ax=plt.subplots(figsize=(8,4))
 for axis in range(3):ax.semilogy(probe['frequencies'],np.max(probe[f'axis_{axis}'],axis=0)/9.80665**2,label='Base '+ 'XYZ'[axis])
 ax.set(xlabel='Frequency (Hz)',ylabel='Maximum probe acceleration PSD (g²/Hz)',title='Separate normalized base excitation cases');ax.grid();ax.legend();fig.tight_layout();fig.savefig(out/'response-psd.png');plt.close(fig)
 fig,ax=plt.subplots(figsize=(8,4));a=fields['acceleration_rms_base_Z'];im=ax.scatter(points[:,0]*1000,points[:,1]*1000,c=np.linalg.norm(a,axis=1)/9.80665,s=5);fig.colorbar(im,ax=ax,label='RSS of acceleration-component RMS (g)');ax.set_aspect('equal');ax.set(xlabel='X (mm)',ylabel='Y (mm)',title='Z-base excitation, 1 g RMS');fig.tight_layout();fig.savefig(out/'board-response.png');plt.close(fig)
 import csv
 with (out/'mass-audit.csv').open('w',newline='') as stream:
  writer=csv.writer(stream);writer.writerow(['reference','MPN','mass_g','estimated','uncertainty_fraction','method','source'])
  for part in physical['components']:writer.writerow([part['ref'],part.get('mpn',''),part['mass_g'],part['estimated'],part['uncertainty_fraction'],part['method'],(part.get('manufacturer_data') or {}).get('source','')])
 with (out/'response-summary.csv').open('w',newline='') as stream:
  writer=csv.writer(stream);writer.writerow(['field','maximum_component_RMS_SI'])
  writer.writerows(psd['maxima'].items())
 estimates=sum(p['estimated'] for p in physical['components'])
 report=f'''# {case['name']}

Status: **{psd['status']}**. Linear vibration screening with assumed rigid mounts.

- Retained modes: {modal['mode_count']}; highest frequency: {modal['coverage_hz']:.1f} Hz.
- Maximum eigenpair residual: {modal['maximum_residual']:.3g}; mass orthogonality error: {modal['mass_orthogonality_error']:.3g}.
- Effective modal mass fractions X/Y/Z: {modal['effective_mass_fraction_xyz']}.
- Excitation: separate X/Y/Z spectra, {psd['input_rms_g']:.6g} g RMS, {case['psd']['frequency_hz'][0]:g}–{case['psd']['frequency_hz'][-1]:g} Hz.
- Modal damping: {case['psd']['damping']*100:g}%; sensitivity cases: {case['psd']['sensitivity_damping']}.
- Integration change: {max(psd['integration_relative_change'].values()):.3%}; modal truncation change: {max(psd['truncation_relative_change'].values()):.3%}.
- Backend: {psd['execution']}.
- Assembled mass: {modal['total_mass_kg_xyz'][0]*1000:.3f} g. Estimated component masses: {estimates}/{len(physical['components'])}.

Generic effective material: E={case['material']['young_pa']/1e9:g} GPa, ν={case['material']['poisson']}, density={case['material']['density_kg_m3']:g} kg/m³. These are not measured board properties. Component stiffness, mass offsets, cables and enclosure flexibility are omitted. Component estimates use attachment envelopes and package-class densities and carry ±50% screening uncertainty. Exact assumptions are in the mass audit.

Residual flexibility is included for displacement, acceleration, stress and strain. Absolute acceleration includes base motion. Stress components are reported separately; RMS von Mises, fatigue life and qualification are not inferred. Contact-edge stress maxima may be mesh-sensitive.

`modes.pvd` contains mass-normalized modes. `animation.pvd` exaggerates the first mode for display; it is not a physical response amplitude. VTK display cells are linearized; the analysis uses quadratic elements. `rms.vtu` contains physical RMS fields.

![Natural frequencies](frequencies.png)
![Response PSD](response-psd.png)
![Board response](board-response.png)
'''
 (out/'report.md').write_text(report)
 write_json(out/'summary.json',{'modal':modal,'psd':psd,'mass_audit':physical})
 # A relocatable ParaView script both opens results and saves a native state.
 (out/'open-view.py').write_text('''from pathlib import Path
from paraview.simple import *
p=Path(__file__).resolve().parent
r=XMLUnstructuredGridReader(FileName=[str(p/'rms.vtu')]);v=GetActiveViewOrCreate('RenderView');d=Show(r,v)
ColorBy(d,('POINTS','acceleration_rms_base_Z','Magnitude'));d.SetScalarBarVisibility(v,True);v.ViewSize=[1200,750];ResetCamera(v);Render(v)
SaveState(str(p/'view.pvsm'));SaveScreenshot(str(p/'paraview-rms.png'),v)
''')
