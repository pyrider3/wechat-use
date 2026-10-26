import hashlib,json,pathlib,tempfile,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_forward')
def row(text,y=200,confidence=.99):return {'text':text,'confidence':confidence,'bounds':[200,y,200,25]}
class ForwardValidationTests(unittest.TestCase):
 def test_recipients_require_exact_complete_set(self):
  self.assertEqual(m.selected_names([row('fixture'),row('other')],['fixture','other']),['fixture','other'])
  with self.assertRaises(ValueError):m.selected_names([row('fixture'),row('wrong')],['fixture','other'])
 def test_duplicate_selected_names_refuse(self):
  with self.assertRaises(ValueError):m.selected_names([row('fixture'),row('fixture')],['fixture','other'])
 def test_low_confidence_recipient_refuses(self):
  with self.assertRaises(ValueError):m.selected_names([row('fixture',confidence=.6)],['fixture'])
 def test_preview_requires_source_and_order(self):
  rows=[row('和文件传输助手的聊天记录',10),row('first',220),row('second',350)]
  m.preview_matches(rows,['first','second'])
  with self.assertRaises(ValueError):m.preview_matches(rows,['second','first'])
  with self.assertRaises(ValueError):m.preview_matches(rows[1:],['first','second'])
 def test_legacy_forward_record_blocks_recipient_subset(self):
  with tempfile.TemporaryDirectory() as t,patch.object(m,'STATE',pathlib.Path(t)):
   (m.STATE/'legacy.json').write_text(json.dumps({'status':'ui_confirmed','source_messages':['first','second'],'recipients':['fixture','other','third']}))
   self.assertIsNotNone(m.known_forward(['first','second'],['fixture','other']))
   self.assertIsNone(m.known_forward(['different','second'],['fixture','other']))
 def test_fingerprint_is_recipient_order_invariant(self):self.assertEqual(m.fingerprint(['a','b'],['x','y']),m.fingerprint(['a','b'],['y','x']))
 def test_sender_binding_refuses_before_any_gui_read(self):
  class Fake:
   def fallback(self,e):return {'isError':True,'content':[]}
  with tempfile.TemporaryDirectory() as t,patch.object(m,'STATE',pathlib.Path(t)):
   op='binding-test-001';p=m.STATE/(hashlib.sha256(op.encode()).hexdigest()+'.json');p.write_text(json.dumps({'status':'sending','recipients':['other','third']}))
   result=m.Forwarder(Fake()).run({'operation_id':op,'recipients':['fixture','other'],'dry_run':False})
   self.assertTrue(result['isError'])
 def test_submitted_request_never_replays(self):
  class Fake:
   def fallback(self,e):return {'isError':True,'content':[]}
  with tempfile.TemporaryDirectory() as t,patch.object(m,'STATE',pathlib.Path(t)):
   op='submitted-test-001';p=m.STATE/(hashlib.sha256(op.encode()).hexdigest()+'.json');p.write_text(json.dumps({'status':'sending','recipients':['fixture','other']}))
   result=m.Forwarder(Fake()).run({'operation_id':op,'recipients':['fixture','other'],'dry_run':False})
   self.assertTrue(result['isError']);self.assertTrue(json.loads(result['content'][0]['text'])['duplicate_request'])
class DryRunTests(unittest.TestCase):
 def test_dry_run_cancels_without_submit(self):
  im=Image.new('RGB',(100,100),'white')
  class Fake:
   def __init__(self):self.proxy=self;self.calls=[]
   def check(self):return {'size':[100,100],'messages':'0,0 100x100','forward':{'checkbox_x':5,'multi_toolbar':[0,0,100,100],'forward_button':[0,0,50,100],'preview_open':[10,10],'preview_close':[10,10]}}
   def im(self,_):return im
   def call(self,n,a):self.calls.append((n,a))
   def fallback(self,e):return {'isError':True,'content':[{'type':'text','text':str(e)}]}
  class F(m.Forwarder):
   def open_source(self):pass
   def source(self):self.source_panel=im;return [{'text':'first','box':(10,10,50,30)},{'text':'second','box':(10,40,50,60)}]
   def capture(self):return im
   def checks(self,*args):return [True,True]
   def click_label(self,*args):pass
   def wait(self,*args,**kwargs):return im
   def click(self,*args):pass
   def select_recipient(self,*args):pass
   def cancel(self):self.cancelled=True
  with tempfile.TemporaryDirectory() as t:
   state=pathlib.Path(t)/'state';profile=pathlib.Path(t)/'profile';profile.write_text('{}');r=Fake();f=F(r);f.ocr=object()
   with patch.object(m,'STATE',state),patch.object(m,'PROFILE',profile):out=f.run({'operation_id':'dry-run-test-001','recipients':['fixture','other']})
  self.assertFalse(out.get('isError'));self.assertTrue(f.cancelled);data=json.loads(out['content'][0]['text']);self.assertEqual(data['messages_sent'],0);self.assertEqual(data['status'],'dry_run_confirmed');self.assertTrue(all(n=='click' and a.get('button')==3 for n,a in r.calls))

class SearchPacingTests(unittest.TestCase):
 def test_search_never_overwrites_pending_paste_with_clipboard_probe(self):
  im=Image.new('RGB',(500,100),'white')
  class Proxy:
   def __init__(self):self.proxy=self;self.calls=[]
   def call(self,n,a):self.calls.append((n,a))
  class F(m.Forwarder):
   def capture(self):return im
  r=Proxy();f=F(r);f.ocr=object()
  with patch.object(m,'focused',return_value=True),patch.object(m.auto,'ocr',return_value=('fixture',99)),patch.object(m.time,'sleep'):f.type_query('fixture',[0,0,406,46])
  self.assertEqual(r.calls,[('key',{'shortcut':'ctrl+a'}),('clipboard_write',{'text':'fixture'}),('key',{'shortcut':'ctrl+v'})])
 def test_search_refuses_unfocused_field(self):
  class R:
   def __init__(self):self.proxy=self;self.calls=[]
   def call(self,n,a):self.calls.append((n,a))
  class F(m.Forwarder):
   def capture(self):return Image.new('RGB',(500,100),'white')
  r=R();f=F(r)
  with self.assertRaises(ValueError):f.type_query('fixture',[0,0,406,46])
  self.assertFalse(r.calls)
