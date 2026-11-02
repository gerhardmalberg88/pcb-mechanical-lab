"""Read-only KiCad outline, supports and fitted-component extraction."""
from pathlib import Path
import re,math
from .common import digest,write_json,WorkflowError
from .masses import CATALOG

def extract(board_path,destination,case):
 import pcbnew
 before=digest(board_path);board=pcbnew.LoadBoard(str(board_path))
 poly=pcbnew.SHAPE_POLY_SET()
 if not board.GetBoardPolygonOutlines(poly,False,None,False,False):raise WorkflowError('Board outline is not closed')
 def ring(c):return [[c.CPoint(i).x/1e6,c.CPoint(i).y/1e6] for i in range(c.PointCount())]
 outlines=[{'outer':ring(poly.COutline(i)),'holes':[ring(poly.CHole(i,j)) for j in range(poly.HoleCount(i))]} for i in range(poly.OutlineCount())]
 parts=[];holes=[]
 for fp in board.GetFootprints():
  ref=fp.GetReference();name=str(fp.GetFPID().GetLibItemName());pads=list(fp.Pads())
  if name.startswith('MountingHole') or ref in case['mounts']['refs']:
   for pad in pads:
    drill=pad.GetDrillSize().x/1e6
    if drill>1.:holes.append({'ref':ref,'center_mm':[pad.GetPosition().x/1e6,pad.GetPosition().y/1e6],'diameter_mm':drill})
   continue
  if fp.IsDNP() or not pads:continue
  xs=[];ys=[]
  for pad in pads:
   b=pad.GetBoundingBox();xs += [b.GetX()/1e6,(b.GetX()+b.GetWidth())/1e6];ys += [b.GetY()/1e6,(b.GetY()+b.GetHeight())/1e6]
  w=max(max(xs)-min(xs),.3);h=max(max(ys)-min(ys),.3)
  fields={f.GetName():f.GetText() for f in fp.GetFields()}
  mpn=fields.get('MPN','').strip();catalog=CATALOG.get(mpn)
  overrides=case['components']['mass_overrides_g'];mass=overrides.get(ref)
  if mass is None and catalog:mass=catalog['mass_g']
  estimated=mass is None
  # Screening estimates; do not imply measured/manufacturer data.
  prefix=ref.rstrip('0123456789');height={'J':8.,'L':3.5,'T':3.,'U':1.2,'C':.8,'R':.6,'F':.8,'D':1.}.get(prefix,1.)
  rho={'J':1.5,'L':4.5,'T':3.,'U':2.,'C':4.,'R':3.9,'F':2.,'D':2.}.get(prefix,2.)
  method='case mass override' if ref in overrides else ('manufacturer nominal mass' if catalog else 'attachment-envelope × package-class height × effective density; estimate')
  if mass is None:mass=w*h*height*rho/1000
  if not math.isfinite(mass) or mass<=0:raise WorkflowError(f'Invalid component mass: {ref}')
  parts.append({'ref':ref,'value':fp.GetValue(),'footprint':name,'box_mm':[min(xs),min(ys),max(xs),max(ys)],'mass_g':mass,'method':method,'mpn':mpn,'manufacturer_data':catalog,'estimated':estimated,'missing_manufacturer_mass':catalog is None,'uncertainty_fraction':.5 if estimated else None,'estimated_height_mm':height,'effective_density_g_cm3':rho})
 if before!=digest(board_path):raise WorkflowError('Snapshot changed while extracting')
 result={'source_sha256':before,'kicad_version':pcbnew.GetBuildVersion(),'units':'mm','thickness_mm':board.GetDesignSettings().GetBoardThickness()/1e6,'outlines':outlines,'mounting_holes':holes,'components':parts if case['components']['enabled'] else [],'excluded_dnp':sum(fp.IsDNP() for fp in board.GetFootprints()),'mass_estimates_are_screening_only':True}
 if case['mounts']['kind']=='holes' and set(case['mounts']['refs'])-set(h['ref'] for h in holes):raise WorkflowError('Requested mounting holes were not found')
 write_json(destination,result);return result
