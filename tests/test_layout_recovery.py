import json,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_regions')
class RecoveryTests(unittest.TestCase):
 def test_resolution_handoff_preserves_user_size(self):
  r=m.Regions(None)
  with patch.object(r,'capture',return_value={'content':[]}),patch.object(m.auto,'image',return_value=Image.new('RGB',(1505,1818))),patch.object(m,'inventory',return_value={'windows':[]}):
   out=r.fallback(ValueError('layout_changed: screen size differs'))
  d=json.loads(out['content'][0]['text']);self.assertEqual(d['status'],'layout_recalibration_required');self.assertEqual(d['actual_size'],[1505,1818]);self.assertTrue(d['preserve_user_resolution']);self.assertEqual(d['next_tool'],'calibrate_regions')
 def test_popup_does_not_trigger_recalibration(self):
  r=m.Regions(None)
  with patch.object(r,'capture',return_value={'content':[]}):out=r.fallback(ValueError('popup_or_extra_window'))
  self.assertEqual(json.loads(out['content'][0]['text'])['status'],'needs_visual_review')
 def test_uncertain_does_not_trigger_recalibration(self):
  r=m.Regions(None)
  with patch.object(r,'capture',return_value={'content':[]}):out=r.fallback(ValueError('SEND_UNCERTAIN layout_changed: screen size differs'))
  self.assertEqual(json.loads(out['content'][0]['text'])['status'],'needs_visual_review')
 def test_batch_pending_retains_original_ids(self):
  import wechat_workflow as w
  from test_workflow import Fake
  items=[{'recipient':'fixture','text':'hello','operation_id':'resolution-test-01'},{'recipient':'second','text':'hello','operation_id':'resolution-test-02'}]
  with patch.object(w,'select',side_effect=ValueError('layout_changed: screen size differs')):
   out=w.run(Fake(),{'messages':items})
  d=json.loads(out['content'][0]['text']);self.assertEqual(d['status'],'workflow_awaiting_calibration');self.assertEqual(d['pending_messages'],items);self.assertEqual(d['resume_tool'],'send_contacts_workflow')
