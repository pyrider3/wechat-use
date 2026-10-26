import fcntl,importlib.util,pathlib,tempfile,unittest
from unittest.mock import patch
from support import load
m=load('manual-guard')
class ViewerPolicyTests(unittest.TestCase):
 def execute(self,folder):
  p=object.__new__(m.Proxy);p.calls=[];p.results=[]
  p.rpc=lambda method,args:(p.calls.append((method,args)) or {'content':[{'type':'text','text':'ok'}]})
  p.emit=p.results.append
  with patch.object(m,'RUNTIME',pathlib.Path(folder)),patch.object(m.pathlib.Path,'home',return_value=pathlib.Path(folder)):
   p.handle({'id':1,'method':'tools/call','params':{'name':'clipboard_write','arguments':{'text':'test'}}})
  return p
 def test_open_viewer_does_not_pause_ai(self):
  with tempfile.TemporaryDirectory() as t:
   with open(pathlib.Path(t)/'wbox-wechat-manual.lock','w') as old,open(pathlib.Path(t)/'wbox-wechat-viewer-instance.lock','w') as new:
    fcntl.flock(old,fcntl.LOCK_EX);fcntl.flock(new,fcntl.LOCK_EX)
    p=self.execute(t);self.assertEqual(len(p.calls),1);self.assertFalse(p.results[0]['result'].get('isError'))
 def test_two_ai_actions_still_cannot_overlap(self):
  with tempfile.TemporaryDirectory() as t:
   with open(pathlib.Path(t)/'wbox-wechat-action.lock','w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);p=self.execute(t)
    self.assertFalse(p.calls);self.assertIn('automation_busy',p.results[0]['result']['content'][0]['text'])
if __name__=='__main__':unittest.main()
