import base64,io,json,pathlib,tempfile,time,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_visual');auto=m.auto
LAYOUT={'size':[1280,900],'header':'550,75 380x48','messages':'540,145 700x500','draft':'550,675 680x125','input':[740,700]}
ITEM={'recipient':'示例联系人','text':'测试正文','operation_id':'visual-fixture-001'}
class Fake:
 def __init__(self):self.proxy=self;self.calls=[];self.changed=False;self.layout=dict(LAYOUT)
 def check(self):return self.layout
 def focus(self):return ('wechat','微信')
 def im(self,region):return Image.new('RGB',(380,48),'black' if self.changed else 'white')
 def capture(self):
  b=io.BytesIO();Image.new('RGB',(1280,900),'white').save(b,format='PNG')
  return {'content':[{'type':'image','data':base64.b64encode(b.getvalue()).decode(),'mimeType':'image/png'}]}
 def call(self,n,a):self.calls.append((n,a));return self.capture()
 def fallback(self,e):return {'isError':True,'content':[{'type':'text','text':str(e)}]}
class VisualTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.patch=patch.object(auto,'STATE',pathlib.Path(self.tmp.name)/'state');self.patch.start();self.addCleanup(self.patch.stop)
 def prepare(self,r=None,**kw):
  r=r or Fake();result=m.prepare(r,ITEM,**kw);data=json.loads(result['content'][0]['text']);return r,data,result
 def resume_args(self,data,**kw):return {'token':data['token'],'confirmed_recipient':ITEM['recipient'],'visual_evidence':'在返回的标题图片中确认完整备注一致',**kw}
 def test_prepare_images_no_send(self):
  r,d,result=self.prepare();self.assertEqual(d['status'],'awaiting_ai_visual_review');self.assertFalse(d['submitted']);self.assertEqual(sum(c['type']=='image' for c in result['content']),2);self.assertFalse(r.calls)
 def test_context_change_blocks_send(self):
  r,d,_=self.prepare();r.changed=True
  with patch.object(auto,'send') as send:
   with self.assertRaisesRegex(ValueError,'context_changed'):m.resume(r,self.resume_args(d))
   send.assert_not_called()
 def test_expired_token_blocks(self):
  r,d,_=self.prepare();r.visual_tokens[d['token']]['expires']=0
  with self.assertRaisesRegex(ValueError,'expired'):m.resume(r,self.resume_args(d))
 def test_recipient_mismatch_consumes(self):
  r,d,_=self.prepare()
  with self.assertRaisesRegex(ValueError,'mismatch'):m.resume(r,self.resume_args(d,confirmed_recipient='其他人'))
  with self.assertRaisesRegex(ValueError,'consumed'):m.resume(r,self.resume_args(d))
 def test_evidence_required(self):
  r,d,_=self.prepare()
  with self.assertRaisesRegex(ValueError,'evidence_required'):m.resume(r,self.resume_args(d,visual_evidence=''))
 def test_layout_change_blocks(self):
  r,d,_=self.prepare();r.layout['input']=[1,1]
  with self.assertRaisesRegex(ValueError,'context_changed'):m.resume(r,self.resume_args(d))
 def test_same_operation_then_remaining_batch(self):
  remaining=[{**ITEM,'operation_id':'visual-fixture-002'}];r,d,_=self.prepare(remaining=remaining,mode={'_search':True})
  ok={'content':[m.content({'status':'ui_confirmed'})]}
  import wechat_workflow
  with patch.object(auto,'send',return_value=ok) as send,patch.object(wechat_workflow,'run',return_value={'content':[]}) as run:
   m.resume(r,self.resume_args(d));self.assertEqual(send.call_args.args[1],ITEM);self.assertTrue(callable(send.call_args.kwargs['visual_guard']));run.assert_called_once_with(r,{'messages':remaining,'_search':True})
  with self.assertRaisesRegex(ValueError,'consumed'):m.resume(r,self.resume_args(d))
 def test_uncertain_never_continues(self):
  r,d,_=self.prepare(remaining=[ITEM])
  import wechat_workflow
  with patch.object(auto,'send',side_effect=RuntimeError('SEND_UNCERTAIN')),patch.object(wechat_workflow,'run') as run:
   result=m.resume(r,self.resume_args(d));self.assertTrue(result['isError']);run.assert_not_called()
 def test_journal_uncertain_never_issues_token(self):
  auto.STATE.mkdir();p=auto.STATE/(auto.hashlib.sha256(ITEM['operation_id'].encode()).hexdigest()+'.json');p.write_text(json.dumps({'status':'send_uncertain','text_hash':auto.hashlib.sha256(ITEM['text'].encode()).hexdigest(),'recipient_hash':auto.hashlib.sha256(ITEM['recipient'].encode()).hexdigest()}))
  layout=pathlib.Path(self.tmp.name)/'layout';layout.write_text(json.dumps(LAYOUT));r=Fake()
  with patch.object(auto,'LAYOUT',layout):result=m.prepare(r,ITEM)
  self.assertTrue(result['isError']);self.assertFalse(hasattr(r,'visual_tokens'));self.assertFalse(r.calls)
 def test_uncertain_not_eligible(self):
  self.assertFalse(m.eligible(RuntimeError('SEND_UNCERTAIN recipient_unverified')));self.assertTrue(m.eligible(ValueError('search_recipient_switch_timeout')));self.assertFalse(m.eligible(ValueError('layout_changed')))
 def test_sender_visual_guard_preserves_draft_and_enter_once(self):
  layout=pathlib.Path(self.tmp.name)/'layout';layout.write_text(json.dumps(LAYOUT));r=Fake();guard_calls=[]
  # One pre-existing matching draft is allowed only on image-reviewed resume.
  with patch.object(auto,'LAYOUT',layout),patch.object(auto,'image',return_value=Image.new('RGB',(1280,900))),patch.object(auto,'last_bubble',side_effect=[None,((60,0,180,40),Image.new('RGB',(100,30)))]),patch.object(auto,'copy_draft',side_effect=[ITEM['text'],ITEM['text'],'']),patch.object(auto,'message_ocr',return_value=(ITEM['text'],99,'original')),patch.object(auto,'ocr',return_value=('',0)),patch.object(auto.time,'sleep'):
   result=auto.send(r,ITEM,regions=r,recipient=ITEM['recipient'],visual_guard=lambda:guard_calls.append(1))
  self.assertFalse(result.get('isError'));self.assertEqual(sum(n=='key' and a.get('shortcut')=='Return' for n,a in r.calls),1);self.assertFalse(any(n=='key' and a.get('shortcut')=='ctrl+v' for n,a in r.calls));self.assertEqual(len(guard_calls),3)
 def test_sender_visual_guard_recheck_prevents_enter(self):
  layout=pathlib.Path(self.tmp.name)/'layout';layout.write_text(json.dumps(LAYOUT));r=Fake()
  with patch.object(auto,'LAYOUT',layout),patch.object(auto,'image',return_value=Image.new('RGB',(1280,900))),patch.object(auto,'last_bubble',return_value=None),patch.object(auto,'copy_draft',side_effect=['',ITEM['text']]),patch.object(auto.time,'sleep'):
   calls=iter([None,ValueError('visual_context_changed')])
   def guard():
    e=next(calls)
    if e:raise e
   with self.assertRaisesRegex(ValueError,'context_changed'):auto.send(r,ITEM,regions=r,recipient=ITEM['recipient'],visual_guard=guard)
  self.assertFalse(any(n=='key' and a.get('shortcut')=='Return' for n,a in r.calls));self.assertFalse(list(auto.STATE.glob('*.json')))
class HandoffTests(unittest.TestCase):
 def test_workflow_title_failure_hands_off_remaining_original_ids(self):
  import wechat_workflow as w
  items=[dict(ITEM),{**ITEM,'recipient':'另一位示例','operation_id':'visual-fixture-002'}]
  result={'content':[m.content({'status':'awaiting_ai_visual_review'})]}
  with patch.object(w,'select',side_effect=ValueError('recipient_switch_timeout')),patch.object(m,'prepare',return_value=result) as prep:
   out=w.run(Fake(),{'messages':items,'_search':False})
  self.assertFalse(out.get('isError'));self.assertEqual(prep.call_args.args[1],items[0]);self.assertEqual(prep.call_args.kwargs['remaining'],items[1:])
 def test_altered_journal_binding_rejected_before_review(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(auto,'STATE',pathlib.Path(tmp)):
   path=auto.STATE/(auto.hashlib.sha256(ITEM['operation_id'].encode()).hexdigest()+'.json');path.write_text(json.dumps({'status':'ui_confirmed','text_hash':'wrong','recipient_hash':auto.hashlib.sha256(ITEM['recipient'].encode()).hexdigest()}))
   lp=pathlib.Path(tmp)/'layout';lp.write_text(json.dumps(LAYOUT));r=Fake()
   with patch.object(auto,'LAYOUT',lp):
    with self.assertRaisesRegex(ValueError,'different text'):m.prepare(r,ITEM)
   self.assertFalse(hasattr(r,'visual_tokens'))
