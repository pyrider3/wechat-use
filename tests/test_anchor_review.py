import json,tempfile,pathlib,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_regions')
import test_regions as fixtures
Proxy=fixtures.Proxy
class AnchorTests(unittest.TestCase):
 def setup_profile(self,tmp):
  p=fixtures.RegionsTests().profile(tmp);d=json.loads(p.read_text());d['anchors']=[{'region':'1,1 10x10','signature':[255]*960}];p.write_text(json.dumps(d));return p
 def test_transient_repaint_recovers_without_rebase(self):
  with tempfile.TemporaryDirectory() as t:
   p=self.setup_profile(t);before=p.read_bytes();r=m.Regions(Proxy())
   with patch.object(m,'PROFILE',p),patch.object(m,'inventory',return_value=fixtures.RegionsTests().inv()),patch.object(r,'im',side_effect=[Image.new('RGB',(10,10),'black'),Image.new('RGB',(10,10),'white')]),patch.object(m.time,'sleep'):
    r.check()
   self.assertEqual(p.read_bytes(),before)
 def test_persistent_difference_reports_region_without_rebase(self):
  with tempfile.TemporaryDirectory() as t:
   p=self.setup_profile(t);before=p.read_bytes();r=m.Regions(Proxy())
   with patch.object(m,'PROFILE',p),patch.object(m,'inventory',return_value=fixtures.RegionsTests().inv()),patch.object(r,'im',return_value=Image.new('RGB',(10,10),'black')),patch.object(m.time,'sleep'):
    with self.assertRaisesRegex(m.LayoutError,'1,1 10x10'):r.check()
   self.assertEqual(p.read_bytes(),before)
 def test_popup_during_retry_is_not_accepted(self):
  with tempfile.TemporaryDirectory() as t:
   p=self.setup_profile(t);first=fixtures.RegionsTests().inv();second=fixtures.RegionsTests().inv();second['windows'].append({'id':2})
   r=m.Regions(Proxy())
   with patch.object(m,'PROFILE',p),patch.object(m,'inventory',side_effect=[first,second]),patch.object(r,'im',return_value=Image.new('RGB',(10,10),'black')),patch.object(m.time,'sleep'):
    with self.assertRaisesRegex(m.LayoutError,'during_recheck'):r.check()
 def test_anchor_error_does_not_demand_size_calibration(self):
  r=m.Regions(Proxy())
  with patch.object(r,'capture',return_value={'content':[]}):out=r.fallback(ValueError('anchor_review_required: example'))
  d=json.loads(out['content'][0]['text']);self.assertEqual(d['status'],'anchor_review_required');self.assertNotIn('next_tool',d)
 def test_reviewed_anchor_inside_draft_refused(self):
  layout={'size':[1280,900],'header':'550,75 380x48','messages':'540,145 700x500','draft':'550,675 680x125','input':[740,700],'anchor_regions':['550,700 200x7','550,132 200x7']}
  r=m.Regions(Proxy())
  with patch.object(m,'inventory',return_value=fixtures.RegionsTests().inv()),patch.object(r,'capture',return_value={}),patch.object(m.auto,'image',return_value=Image.new('RGB',(1280,900))):
   with self.assertRaisesRegex(ValueError,'overlaps dynamic draft'):r.calibrate(layout)
