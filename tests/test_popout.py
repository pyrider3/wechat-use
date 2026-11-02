import json,tempfile,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_regions')
import test_regions as fixtures
MAIN={'id':1,'x':0,'y':0,'width':1264,'height':900,'override_redirect':False}
POP={'id':2,'x':0,'y':100,'width':700,'height':500,'override_redirect':False}
def wins(*titles,active=1):return {'windows':[{'app_id':'wechat','title':t,'activated':i==active} for i,t in enumerate(titles)]}
class Proxy(fixtures.Proxy):
 def __init__(self,listing):super().__init__();self.listing=listing;self.acting=True
 def call(self,n,a):
  self.calls.append((n,a))
  if n=='list_windows':return {'content':[{'type':'text','text':json.dumps(self.listing)}]}
  return {'content':[{'type':'image','data':'fake','mimeType':'image/png'}]}
class PopoutTests(unittest.TestCase):
 def inv(self,*extra):return {'size':[1280,900],'windows':[MAIN,*extra]}
 def run_check(self,inv_sequence,proxy,ocr=('goodman',95)):
  with tempfile.TemporaryDirectory() as t,patch.object(m,'PROFILE',fixtures.RegionsTests().profile(t)),patch.object(m,'inventory',side_effect=inv_sequence),patch.object(m.time,'sleep'):
   r=m.Regions(proxy)
   with patch.object(r,'im',return_value=Image.new('RGB',(5,5))),patch.object(r,'recognize',return_value=ocr):return r.check()
 def test_verified_chat_popout_is_closed_once(self):
  p=Proxy(wins('微信','goodman',active=1))
  self.run_check([self.inv(POP),self.inv(POP),self.inv(),self.inv()],p)
  clicks=[a for n,a in p.calls if n=='click'];self.assertEqual(clicks,[{'x':660,'y':130}])
 def test_not_closed_without_action_lock(self):
  p=Proxy(wins('微信','goodman'));p.acting=False
  with self.assertRaisesRegex(m.LayoutError,'popup_or_extra_window'):self.run_check([self.inv(POP)],p)
  self.assertFalse([c for c in p.calls if c[0]=='click'])
 def test_title_mismatch_is_not_closed(self):
  p=Proxy(wins('微信','goodman'))
  with self.assertRaisesRegex(m.LayoutError,'popup_or_extra_window'):self.run_check([self.inv(POP),self.inv(POP)],p,ocr=('Settings',95))
  self.assertFalse([c for c in p.calls if c[0]=='click'])
 def test_override_redirect_or_oversized_window_is_not_touched(self):
  for extra in ({**POP,'override_redirect':True},{**POP,'width':1264}):
   p=Proxy(wins('微信','goodman'))
   with self.assertRaisesRegex(m.LayoutError,'popup_or_extra_window'):self.run_check([self.inv(extra)],p)
   self.assertFalse([c for c in p.calls if c[0] in('click','key')])
 def test_unknown_second_window_title_is_not_touched(self):
  p=Proxy(wins('微信','微信'))
  with self.assertRaisesRegex(m.LayoutError,'popup_or_extra_window'):self.run_check([self.inv(POP)],p)
  self.assertFalse([c for c in p.calls if c[0] in('click','key')])
if __name__=='__main__':unittest.main()
