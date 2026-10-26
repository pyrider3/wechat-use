import importlib.util,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_regions')
class Proxy:
 def __init__(self):self.calls=[]
 def focus(self):return ('wechat','微信')
 def call(self,n,a):self.calls.append((n,a));return {'content':[{'type':'image','data':'fake','mimeType':'image/png'}]}
class RegionsTests(unittest.TestCase):
 def profile(self,t):
  p=pathlib.Path(t)/'profile.json';p.write_text(json.dumps({'layout':{'size':[1280,900]},'geometry':{'x':0,'y':0,'width':1264,'height':900},'anchors':[]}));return p
 def inv(self,**kw):
  r={'size':[1280,900],'windows':[{'id':1,'x':0,'y':0,'width':1264,'height':900,'override_redirect':False}]};r.update(kw);return r
 def test_normal_geometry_without_full_capture(self):
  with tempfile.TemporaryDirectory() as t,patch.object(m,'PROFILE',self.profile(t)),patch.object(m,'inventory',return_value=self.inv()):
   p=Proxy();r=m.Regions(p);r.check();self.assertEqual(r.full_frames,0);self.assertFalse(p.calls)
 def test_popup_returns_fresh_full_image_and_no_action(self):
  inv=self.inv();inv['windows'].append({'id':2,'override_redirect':True})
  with tempfile.TemporaryDirectory() as t,patch.object(m,'PROFILE',self.profile(t)),patch.object(m,'inventory',return_value=inv):
   p=Proxy();r=m.Regions(p).run('inspect_regions',{})
   self.assertTrue(r['isError']);self.assertIn('popup_or_extra_window',r['content'][0]['text']);self.assertEqual(p.calls,[('screenshot',{})])
 def test_resize_returns_full_image_without_old_coordinates(self):
  inv=self.inv();inv['windows'][0]['width']=1280
  with tempfile.TemporaryDirectory() as t,patch.object(m,'PROFILE',self.profile(t)),patch.object(m,'inventory',return_value=inv):
   p=Proxy();r=m.Regions(p).run('inspect_regions',{})
   self.assertTrue(r['isError']);self.assertIn('layout_changed',r['content'][0]['text']);self.assertEqual(p.calls,[('screenshot',{})])
 def test_cache_reused_only_for_identical_pixels(self):
  p=Proxy();r=m.Regions(p)
  with patch.object(m.auto,'ocr',return_value=('文件传输助手',96)) as ocr:
   r.recognize(Image.new('RGB',(20,20),'white'));r.recognize(Image.new('RGB',(20,20),'white'));r.recognize(Image.new('RGB',(20,20),'black'))
   self.assertEqual(ocr.call_count,2)
 def test_anchor_difference_detected(self):
  with tempfile.TemporaryDirectory() as t:
   p=self.profile(t);d=json.loads(p.read_text());d['anchors']=[{'region':'1,1 10x10','signature':[255]*960}];p.write_text(json.dumps(d))
   with patch.object(m,'PROFILE',p),patch.object(m,'inventory',return_value=self.inv()):
    r=m.Regions(Proxy());r.im=lambda _:Image.new('RGB',(10,10),'black')
    with self.assertRaisesRegex(m.LayoutError,'anchor differs'):r.check()
if __name__=='__main__':unittest.main()
