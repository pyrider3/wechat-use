import json,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_workflow')
class Fake:
 def __init__(self,headers=None):self.proxy=self;self.calls=[];self.headers=iter(headers or [('fixture',99)]*5)
 def check(self):return {'size':[1280,900],'header':'550,75 380x48'}
 def im(self,_):return Image.new('RGB',(100,100),'white')
 def header(self):return next(self.headers)
 def call(self,n,a):self.calls.append((n,a));return {'content':[]}
 def fallback(self,e):return {'isError':True,'content':[{'type':'text','text':str(e)}]}
class WorkflowTests(unittest.TestCase):
 def row(self,**kw):r={'text':'fixture','confidence':99,'x':5,'y':20,'width':100,'height':26};r.update(kw);return r
 def test_duplicate_names_refuse(self):
  with self.assertRaisesRegex(ValueError,'not_unique'):m.unique([self.row(),self.row(y=140)],'fixture')
 def test_low_confidence_refuse(self):
  with self.assertRaisesRegex(ValueError,'low_confidence'):m.unique([self.row(confidence=70)],'fixture')
 def test_missing_contact_does_not_click(self):
  p=Fake()
  with patch.object(m,'lines',return_value=[]):
   with self.assertRaises(ValueError):m.select(p,'fixture')
  self.assertFalse(p.calls)
 def test_list_changes_before_click_refuse(self):
  p=Fake();p.im=iter([Image.new('RGB',(10,10),'white'),Image.new('RGB',(10,10),'black')]).__next__
  p.im=lambda _,seq=iter([Image.new('RGB',(10,10),'white'),Image.new('RGB',(10,10),'black')]):next(seq)
  with patch.object(m,'lines',return_value=[self.row()]):
   with self.assertRaisesRegex(ValueError,'list_changed'):m.select(p,'fixture')
  self.assertFalse(p.calls)
 def test_waits_for_two_exact_titles(self):
  p=Fake([('wrong',99),('fixture',99),('fixture',99)])
  with patch.object(m,'lines',return_value=[self.row()]),patch.object(m.time,'sleep'):
   r=m.select(p,'fixture')
  self.assertEqual(len(p.calls),1);self.assertIn('wait_title_ms',r)
 def test_validates_whole_batch_before_selection(self):
  p=Fake()
  with patch.object(m,'select') as select:
   result=m.run(p,{'messages':[{'recipient':'fixture','text':'hello','operation_id':'valid-id-01'},{'recipient':'second','text':'bad\n','operation_id':'valid-id-02'}]})
  self.assertTrue(result['isError']);select.assert_not_called()
 def test_uncertain_stops_batch(self):
  p=Fake();items=[{'recipient':'fixture','text':'hello','operation_id':'unique-test-id-01'},{'recipient':'other','text':'world','operation_id':'unique-test-id-02'}]
  with patch.object(m,'select',return_value={}) as select,patch.object(m.auto,'send',side_effect=RuntimeError('SEND_UNCERTAIN')) as send:
   r=m.run(p,{'messages':items})
  self.assertTrue(r['isError']);self.assertEqual(send.call_count,1);self.assertEqual(select.call_count,1)

class WorkflowSuccessTests(unittest.TestCase):
 def test_success_batch_keeps_distinct_recipient_and_text(self):
  p=Fake();items=[{'recipient':'fixture','text':'hello','operation_id':'success-fixture-001'},{'recipient':'other','text':'world','operation_id':'success-other-002'}]
  result={'content':[{'type':'text','text':json.dumps({'status':'ui_confirmed'})}]}
  with patch.object(m,'select',return_value={'select_ms':1}) as select,patch.object(m.auto,'send',return_value=result) as send:
   r=m.run(p,{'messages':items})
  self.assertFalse(r.get('isError'));self.assertEqual([c.kwargs['recipient'] for c in send.call_args_list],['fixture','other']);self.assertEqual([c.args[1]['text'] for c in send.call_args_list],['hello','world'])
 def test_preview_without_clock_is_not_a_contact(self):
  import subprocess
  header='page_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n'
  data=header+'1\t1\t1\t1\t10\t10\t100\t25\t99\tfixture\n'
  with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout=data.encode())):
   self.assertEqual(m.lines(Image.new('RGB',(330,100))),[])
