import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('auto_file_helper')
class Fake:
 def __init__(self):self.calls=[]
 def focus(self):return ('wechat','微信')
 def call(self,name,args):self.calls.append((name,args));return {'content':[]}
class AutoTests(unittest.TestCase):
 def setup_state(self,folder):
  layout=pathlib.Path(folder)/'layout.json';layout.write_text(json.dumps({'size':[1280,900],'header':'550,75 380x48','messages':'540,145 700x500','draft':'550,675 680x125','input':[740,700]}));return patch.multiple(m,STATE=pathlib.Path(folder)/'state',LAYOUT=layout)
 def test_normalization(self):self.assertEqual(m.norm('你好： A7\n'),m.norm('你好: A7'))
 def test_wrong_recipient_never_mutates(self):
  with tempfile.TemporaryDirectory() as t,self.setup_state(t),patch.object(m,'image',return_value=Image.new('RGB',(1280,900))),patch.object(m,'ocr',return_value=('其他好友',99)):
   p=Fake()
   with self.assertRaisesRegex(ValueError,'recipient_unverified'):m.send(p,{'text':'测试','operation_id':'test-wrong-01'})
   self.assertTrue(all(n=='screenshot' for n,a in p.calls))
 def test_layout_change_never_mutates(self):
  with tempfile.TemporaryDirectory() as t,self.setup_state(t),patch.object(m,'image',return_value=Image.new('RGB',(1000,800))):
   p=Fake()
   with self.assertRaisesRegex(ValueError,'layout_changed'):m.send(p,{'text':'测试','operation_id':'test-layout-01'})
   self.assertTrue(all(n=='screenshot' for n,a in p.calls))
 def test_low_confidence_recipient_never_mutates(self):
  with tempfile.TemporaryDirectory() as t,self.setup_state(t),patch.object(m,'image',return_value=Image.new('RGB',(1280,900))),patch.object(m,'ocr',return_value=('文件传输助手',60)):
   p=Fake()
   with self.assertRaisesRegex(ValueError,'recipient_unverified'):m.send(p,{'text':'测试','operation_id':'test-lowconf-01'})
   self.assertTrue(all(n=='screenshot' for n,a in p.calls))
 def test_duplicate_request_no_upstream_calls(self):
  with tempfile.TemporaryDirectory() as t,self.setup_state(t):
   m.STATE.mkdir();op='test-duplicate-01';text='测试';p=m.STATE/(m.hashlib.sha256(op.encode()).hexdigest()+'.json');p.write_text(json.dumps({'status':'ui_confirmed','text_hash':m.hashlib.sha256(text.encode()).hexdigest()}))
   proxy=Fake();r=m.send(proxy,{'text':text,'operation_id':op})
   self.assertFalse(proxy.calls);self.assertIn('duplicate_request',r['content'][0]['text'])
 def test_uncertain_request_never_replays(self):
  with tempfile.TemporaryDirectory() as t,self.setup_state(t):
   m.STATE.mkdir();op='test-uncertain-01';text='测试';p=m.STATE/(m.hashlib.sha256(op.encode()).hexdigest()+'.json');p.write_text(json.dumps({'status':'send_uncertain','text_hash':m.hashlib.sha256(text.encode()).hexdigest()}))
   proxy=Fake();r=m.send(proxy,{'text':text,'operation_id':op})
   self.assertFalse(proxy.calls);self.assertTrue(r['isError'])
class ContactTests(unittest.TestCase):
 setup_state=AutoTests.setup_state
 def test_contact_mismatch_no_mutation(self):
  with tempfile.TemporaryDirectory() as t,self.setup_state(t),patch.object(m,'image',return_value=Image.new('RGB',(1280,900))),patch.object(m,'ocr',return_value=('another_contact',99)):
   p=Fake()
   with self.assertRaisesRegex(ValueError,'recipient_unverified'):m.send(p,{'text':'测试','operation_id':'contact-wrong-01'},recipient='fixture_contact')
   self.assertTrue(all(n=='screenshot' for n,a in p.calls))
 def test_recipient_match_is_case_sensitive(self):
  with tempfile.TemporaryDirectory() as t,self.setup_state(t),patch.object(m,'image',return_value=Image.new('RGB',(1280,900))),patch.object(m,'ocr',return_value=('Fixture',99)):
   with self.assertRaisesRegex(ValueError,'recipient_unverified'):m.send(Fake(),{'text':'测试','operation_id':'contact-case-01'},recipient='fixture')
 def test_cross_recipient_operation_rejected(self):
  with tempfile.TemporaryDirectory() as t,self.setup_state(t):
   m.STATE.mkdir();op='contact-bound-01';text='测试';p=m.STATE/(m.hashlib.sha256(op.encode()).hexdigest()+'.json');p.write_text(json.dumps({'status':'ui_confirmed','text_hash':m.hashlib.sha256(text.encode()).hexdigest(),'recipient_hash':m.hashlib.sha256(b'first').hexdigest()}))
   proxy=Fake()
   with self.assertRaisesRegex(ValueError,'different recipient'):m.send(proxy,{'text':text,'operation_id':op},recipient='second')
   self.assertFalse(proxy.calls)
 def test_matching_contact_preserves_existing_draft(self):
  with tempfile.TemporaryDirectory() as t,self.setup_state(t),patch.object(m,'image',return_value=Image.new('RGB',(1280,900))),patch.object(m,'ocr',return_value=('fixture_contact',99)),patch.object(m,'last_bubble',return_value=None),patch.object(m,'copy_draft',return_value='existing draft'):
   p=Fake()
   with self.assertRaisesRegex(ValueError,'draft_not_empty'):m.send(p,{'text':'测试','operation_id':'contact-draft-01'},recipient='fixture_contact')
   self.assertFalse(any(n=='key' and a.get('shortcut')=='Return' for n,a in p.calls))
if __name__=='__main__':unittest.main()
