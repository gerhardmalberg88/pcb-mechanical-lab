"""Layered quadratic tetrahedral meshes with explicit finite mounting contacts."""
from pathlib import Path
import json,math
from .common import write_json,WorkflowError

def generate(extracted,case,out):
 import gmsh
 out=Path(out);out.mkdir(parents=True,exist_ok=True);g=case['mesh'];t=extracted['thickness_mm']*.001
 gmsh.initialize();gmsh.option.setNumber('General.NumThreads',case['execution']['threads']);gmsh.model.add('pcb')
 occ=gmsh.model.occ
 def wire(points):
  tags=[occ.addPoint(x*.001,y*.001,0) for x,y in points]
  return occ.addCurveLoop([occ.addLine(tags[i],tags[(i+1)%len(tags)]) for i in range(len(tags))])
 try:
  surfaces=[]
  for o in extracted['outlines']:
   surfaces.append((2,occ.addPlaneSurface([wire(o['outer'])]+[wire(r) for r in o['holes']])))
  holes=[h for h in extracted['mounting_holes'] if h['ref'] in case['mounts']['refs']]
  if holes:
   disks=[(2,occ.addDisk(h['center_mm'][0]*.001,h['center_mm'][1]*.001,0,h['diameter_mm']*.0005,h['diameter_mm']*.0005)) for h in holes]
   surfaces,_=occ.cut(surfaces,disks)
   disks=[(2,occ.addDisk(h['center_mm'][0]*.001,h['center_mm'][1]*.001,0,case['mounts']['outer_diameter_mm']*.0005,case['mounts']['outer_diameter_mm']*.0005)) for h in holes]
   surfaces,_=occ.fragment(surfaces,disks)
   # Fragments inside the drill disks were introduced by the outer disks.
   keep=[]
   for dim,tag in surfaces:
    area=occ.getMass(dim,tag);cx,cy,_=occ.getCenterOfMass(dim,tag)
    inside=any(math.hypot(cx-h['center_mm'][0]*.001,cy-h['center_mm'][1]*.001)<1e-7 and area<math.pi*(h['diameter_mm']*.0005)**2*1.01 for h in holes)
    if inside:occ.remove([(dim,tag)],recursive=True)
    else:keep.append((dim,tag))
   surfaces=keep
  occ.synchronize()
  occ.extrude(surfaces,0,0,t,numElements=[g['layers']],recombine=False)
  occ.synchronize()
  vols=gmsh.model.getEntities(3)
  external=gmsh.model.getBoundary(vols,combined=True,oriented=False,recursive=False)
  minx=min(x for o in extracted['outlines'] for x,y in o['outer'])*.001
  fixed=[];free=[]
  for dim,tag in external:
   bb=occ.getBoundingBox(dim,tag);cx,cy,cz=occ.getCenterOfMass(dim,tag)
   if case['mounts']['kind']=='cantilever':isfixed=abs(bb[0]-minx)<2e-7 and abs(bb[3]-minx)<2e-7
   else:
    flat=bb[5]-bb[2]<3e-7
    isfixed=flat and any(math.hypot(cx-h['center_mm'][0]*.001,cy-h['center_mm'][1]*.001)<case['mounts']['outer_diameter_mm']*.0005 for h in holes)
   (fixed if isfixed else free).append(tag)
  if not fixed:raise WorkflowError('No finite mounting contact surfaces found')
  gmsh.model.addPhysicalGroup(3,[tag for _,tag in vols],1);gmsh.model.setPhysicalName(3,1,'board')
  gmsh.model.addPhysicalGroup(2,fixed,2);gmsh.model.setPhysicalName(2,2,'fixed')
  gmsh.model.addPhysicalGroup(2,free,3);gmsh.model.setPhysicalName(2,3,'free')
  gmsh.model.mesh.setSize(gmsh.model.getEntities(0),g['size_mm']*.001)
  for dim,tag in gmsh.model.getEntities(0):
   x,y,z=gmsh.model.getValue(dim,tag,[])
   if any(math.hypot(x-h['center_mm'][0]*.001,y-h['center_mm'][1]*.001)<case['mounts']['outer_diameter_mm']*.0006 for h in holes):gmsh.model.mesh.setSize([(dim,tag)],g['mount_size_mm']*.001)
  gmsh.option.setNumber('Mesh.MeshSizeMax',g['size_mm']*.001)
  gmsh.option.setNumber('Mesh.MeshSizeMin',min(g['size_mm'],g['mount_size_mm'])*.001)
  # Polygonized KiCad arcs contain short edges. Propagating their edge length
  # across the plate overrides the requested in-plane spacing. Use an explicit
  # size field and preserve every outline vertex instead.
  gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary',0)
  gmsh.option.setNumber('Mesh.MeshSizeFromPoints',0)
  field=gmsh.model.mesh.field.add('MathEval')
  size=g['size_mm']*.001
  expression=str(size)
  if holes:
   distances=[f'Sqrt((x-{h["center_mm"][0]*.001})^2+(y-{h["center_mm"][1]*.001})^2)' for h in holes]
   expression=f'Min({size}, {g["mount_size_mm"]*.001}+0.3*Max(0,Min('+','.join(distances)+f')-{case["mounts"]["outer_diameter_mm"]*.0005}))'
  gmsh.model.mesh.field.setString(field,'F',expression)
  gmsh.model.mesh.field.setAsBackgroundMesh(field)
  gmsh.option.setNumber('Mesh.SecondOrderIncomplete',1)
  gmsh.model.mesh.generate(3);gmsh.model.mesh.setOrder(2)
  n=len(gmsh.model.mesh.getNodes()[0]);dofs=3*n
  if dofs>g['max_dofs']:raise WorkflowError(f'Mesh has {dofs} displacement DOFs; limit {g["max_dofs"]}; choose an explicit smaller model')
  gmsh.option.setNumber('Mesh.MshFileVersion',2.2);gmsh.option.setNumber('Mesh.Binary',0)
  gmsh.write(str(out/'board.msh'));gmsh.write(str(out/'geometry.brep'))
  (out/'geometry.geo').write_text('Merge "geometry.brep";\n')
  write_json(out/'mesh-summary.json',{'nodes':n,'dofs':dofs,'quadratic':True,'through_thickness_layers':g['layers'],'fixed_surfaces':fixed,'mesh':g})
 finally:gmsh.finalize()
