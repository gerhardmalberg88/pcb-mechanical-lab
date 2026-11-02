import unittest
from unittest.mock import patch
import numpy as np
from scipy.integrate import quad
from pcb_mechanical.psd import covariance,rms_field,G
from pcb_mechanical.config import DEFAULTS,merge,validate
from pcb_mechanical.common import WorkflowError
from pcb_mechanical.runtime import Runtime

class Physics(unittest.TestCase):
 def test_sdof_white_noise(self):
  fn=100.;z=.02;w=2*np.pi*fn;f=np.unique(np.r_[np.linspace(.001,3000,25000),np.linspace(90,110,4000)])
  p={'frequency_hz':[.001,3000.],'density_g2_hz':[1/G**2,1/G**2]}
  c,ca,q,s=covariance(np.array([fn]),np.array([[1.,0.,0.]]),0,f,p,z,np)
  value=rms_field(np.array([[1.,0.,0.]]),c,np)[0]**2
  analytical=1/(8*z*w**3)
  self.assertLess(abs(value/analytical-1),2e-4)
 def test_damping_and_absolute_acceleration_against_quadrature(self):
  fn=120.;wn=2*np.pi*fn;f=np.unique(np.r_[np.linspace(20,2000,20001),np.linspace(100,140,8001)])
  p={'frequency_hz':[20,2000],'density_g2_hz':[1/1980]*2};values=[]
  for z in (.01,.02,.05):
   c,ca,_,_=covariance(np.array([fn]),np.array([[1.,0.,0.]]),0,f,p,z,np)
   values.append(rms_field(np.array([[1.,0.,0.]]),c,np)[0])
   measured=rms_field(np.array([[1.,0.,1.]]),ca,np)[0]**2
   def spectrum(hz):
    w=2*np.pi*hz;h=(wn**2+2j*z*wn*w)/(wn**2-w**2+2j*z*wn*w)
    return abs(h)**2*G**2/1980
   reference=quad(spectrum,20,2000,points=[fn],epsabs=1e-9)[0]
   self.assertLess(abs(measured/reference-1),1e-4)
  self.assertGreater(values[0],values[1]);self.assertGreater(values[1],values[2])
 def test_modes_remain_coherent(self):
  f=np.linspace(20,2000,10000);p={'frequency_hz':[20,2000],'density_g2_hz':[1/1980]*2}
  c,_,_,_=covariance(np.array([100.,100.]),np.array([[1.,0.,0.],[1.,0.,0.]]),0,f,p,.02,np)
  value=rms_field(np.array([[1.,-1.,0.,0.]]),c,np)[0]
  self.assertLess(value,1e-10)
 def test_absolute_acceleration_includes_base(self):
  f=np.linspace(.1,1,100);p={'frequency_hz':[.1,1.],'density_g2_hz':[1/G**2]*2}
  _,c,_,_=covariance(np.array([100.]),np.array([[1.,0.,0.]]),0,f,p,.02,np)
  value=rms_field(np.array([[1.,0.,1.]]),c,np)[0]
  self.assertAlmostEqual(value,np.sqrt(.9),places=4)
 def test_normalized_input(self):
  p=DEFAULTS['psd'];self.assertAlmostEqual(np.trapz(p['density_g2_hz'],p['frequency_hz']),1.)
 def test_invalid_psd(self):
  for change in ({'frequency_hz':[100,20]},{'density_g2_hz':[-1,0]},{'damping':0}):
   with self.assertRaises(WorkflowError):validate(merge(DEFAULTS,{'psd':change}))
 def test_cpu_does_not_probe_gpu(self):
  with patch.object(Runtime,'image_exists',return_value=True),patch.object(Runtime,'gpu_check',side_effect=AssertionError('GPU probe')):
   self.assertEqual(Runtime().select('cpu')[0],'cpu')
 def test_explicit_gpu_fails(self):
  with patch.object(Runtime,'gpu_check',return_value=(False,'missing')):
   with self.assertRaises(WorkflowError):Runtime().select('cuda')
 def test_auto_reports_fallback(self):
  with patch.object(Runtime,'gpu_check',return_value=(False,'missing')),patch.object(Runtime,'image_exists',return_value=True):
   backend,reason=Runtime().select('auto');self.assertEqual(backend,'cpu');self.assertIn('missing',reason)
if __name__=='__main__':unittest.main()
