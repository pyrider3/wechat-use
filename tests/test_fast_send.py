import importlib.util,json,pathlib,time,unittest
from unittest.mock import patch
from support import load
mod=load('manual-guard')
class GuardTests(unittest.TestCase):
 def proxy(self,actual='测试',header='header'):
  p=object.__new__(mod.Proxy);p.tokens={'token':{'time':time.monotonic(),'focus':('wechat','微信'),'header':'header','region':'0,0 20x10','text':'测试'}}
  p.focus=lambda:('wechat','微信');p.header=lambda _:header;p.calls=[]
  def call(name,args):
   p.calls.append((name,args))
   if name=='clipboard_read':return {'content':[{'type':'text','text':actual}]}
   return {'content':[]}
  p.call=call;return p
 def test_send_once_and_reject_replay(self):
  p=self.proxy()
  with patch.object(mod.time,'sleep'):
   p.fast('send_prepared',{'token':'token'})
   with self.assertRaisesRegex(ValueError,'invalid_or_expired'):p.fast('send_prepared',{'token':'token'})
  self.assertEqual(sum(n=='key' and a['shortcut']=='Return' for n,a in p.calls),1)
 def test_changed_chat_consumes_token_without_sending(self):
  p=self.proxy(header='other chat')
  with self.assertRaisesRegex(RuntimeError,'context_changed'):p.fast('send_prepared',{'token':'token'})
  self.assertFalse(p.calls);self.assertNotIn('token',p.tokens)
 def test_changed_draft_refuses_send(self):
  p=self.proxy(actual='different draft')
  with patch.object(mod.time,'sleep'):
   with self.assertRaisesRegex(RuntimeError,'draft_changed'):p.fast('send_prepared',{'token':'token'})
  self.assertFalse(any(n=='key' and a['shortcut']=='Return' for n,a in p.calls))
 def test_capture_failure_after_enter_is_uncertain(self):
  p=self.proxy();original=p.call
  def call(n,a):
   if n=='screenshot':raise RuntimeError('capture failed')
   return original(n,a)
  p.call=call
  with patch.object(mod.time,'sleep'):
   with self.assertRaisesRegex(RuntimeError,'SEND_UNCERTAIN'):p.fast('send_prepared',{'token':'token'})
  self.assertNotIn('token',p.tokens)
if __name__=='__main__':unittest.main()
