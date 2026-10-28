import copy,json,pathlib,tempfile,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_regions')
import test_regions as fixtures
class RetestFixes(unittest.TestCase):
 def layout(self):return {'size':[1280,900],'header':'550,75 380x48','messages':'540,145 700x500','draft':'550,675 680x125','input':[740,700]}
 def test_empty_explicit_anchors_are_rejected(self):
  layout=self.layout();layout['anchor_regions']=[];r=m.Regions(fixtures.Proxy())
  with patch.object(m,'inventory',return_value=fixtures.RegionsTests().inv()),patch.object(r,'capture',return_value={}),patch.object(m.auto,'image',return_value=Image.new('RGB',(1280,900))):
   with self.assertRaisesRegex(ValueError,'2-6'):r.calibrate(layout)
 def test_calibration_race_does_not_overwrite_profile(self):
  r=m.Regions(fixtures.Proxy());first=fixtures.RegionsTests().inv();second=copy.deepcopy(first);second['windows'][0]['width']=1280
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile';p.write_text('original')
   with patch.object(m,'PROFILE',p),patch.object(m,'inventory',side_effect=[first,second]),patch.object(r,'capture',return_value={}),patch.object(m.auto,'image',return_value=Image.new('RGB',(1280,900))):
    with self.assertRaisesRegex(m.LayoutError,'nothing saved'):r.calibrate(self.layout())
   self.assertEqual(p.read_text(),'original')
 def test_calibration_positive_saves_new_anchor_version(self):
  r=m.Regions(fixtures.Proxy())
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile';lp=pathlib.Path(t)/'layout'
   with patch.object(m,'PROFILE',p),patch.object(m.auto,'LAYOUT',lp),patch.object(m,'inventory',return_value=fixtures.RegionsTests().inv()),patch.object(r,'capture',return_value={}),patch.object(m.auto,'image',return_value=Image.new('RGB',(1280,900))):r.calibrate(self.layout())
   saved=json.loads(p.read_text());self.assertEqual(saved['anchor_version'],2);self.assertEqual(len(saved['anchors']),2);self.assertEqual(json.loads(lp.read_text()),self.layout())
 def test_recheck_layout_change_has_recovery_handoff(self):
  r=m.Regions(fixtures.Proxy())
  with patch.object(r,'capture',return_value={'content':[]}),patch.object(m.auto,'image',return_value=Image.new('RGB',(1505,1818))),patch.object(m,'inventory',return_value=fixtures.RegionsTests().inv()):out=r.fallback(ValueError('layout_changed_during_recheck: changed'))
  self.assertEqual(json.loads(out['content'][0]['text'])['status'],'layout_recalibration_required')
 def test_popup_action_does_not_direct_recalibration(self):
  r=m.Regions(fixtures.Proxy())
  with patch.object(r,'capture',return_value={'content':[]}):out=r.fallback(ValueError('popup_or_extra_window'))
  self.assertIn('Do not recalibrate',json.loads(out['content'][0]['text'])['action'])
 def test_partitioned_sender_does_not_repeat_precheck(self):
  r=m.Regions(fixtures.Proxy())
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile';p.touch()
   with patch.object(m,'PROFILE',p),patch.object(r,'check') as check,patch.object(m.auto,'send',return_value={'content':[]}) as send:
    r.run('send_partitioned_to_contact',{'recipient':'fixture'})
   check.assert_not_called();send.assert_called_once()

 def test_unreadable_title_does_not_request_layout_calibration(self):
  r=m.Regions(fixtures.Proxy())
  with patch.object(r,'capture',return_value={'content':[]}):out=r.fallback(ValueError('title_unreadable'))
  data=json.loads(out['content'][0]['text']);self.assertEqual(data['status'],'title_visual_review_required');self.assertIn('do NOT recalibrate',data['action'])
