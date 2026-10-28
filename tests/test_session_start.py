import io,json,pathlib,tempfile,unittest,fcntl,subprocess,sys
from unittest.mock import patch,Mock
from support import load
m=load('session')
class SessionTests(unittest.TestCase):
 def test_existing_desktop_not_launched_or_stopped(self):
  with tempfile.TemporaryDirectory() as t,patch.object(m,'RUNTIME',pathlib.Path(t)),patch.object(m,'running',return_value=True),patch.object(m.subprocess,'Popen') as popen:m.serve()
  popen.assert_not_called()
 def test_cold_launch_keeps_stdin_open_releases_action_lock(self):
  with tempfile.TemporaryDirectory() as t:
   runtime=pathlib.Path(t);p=Mock();p.stdin=io.StringIO();p.poll.side_effect=[None,None];p.returncode=0
   def wait(timeout):
    with (runtime/'wbox-wechat-action.lock').open('a') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    self.assertFalse(p.stdin.closed);return 0
   p.wait.side_effect=wait
   with patch.object(m,'RUNTIME',runtime),patch.object(m,'running',side_effect=[False,True,False]),patch.object(m.subprocess,'Popen',return_value=p),patch.object(m,'request',side_effect=[{}, {'content':[]}]) as req:
    m.serve()
   self.assertEqual(req.call_args_list[1].args[2],'tools/call');self.assertEqual(req.call_args_list[1].args[3]['name'],'launch');p.terminate.assert_called_once()
 def test_failed_launch_not_accepted(self):
  p=Mock()
  with tempfile.TemporaryDirectory() as t,patch.object(m,'RUNTIME',pathlib.Path(t)),patch.object(m,'running',return_value=False),patch.object(m.subprocess,'Popen',return_value=p),patch.object(m,'request',side_effect=[{}, {'isError':True}]):
   with self.assertRaisesRegex(RuntimeError,'未成功启动'):m.serve()
  p.terminate.assert_called_once()
 def test_rpc_skips_notifications_and_reads_matching_result(self):
  script="import sys,json\nr=json.loads(sys.stdin.readline());print(json.dumps({'jsonrpc':'2.0','method':'notice'}),flush=True);print(json.dumps({'id':r['id'],'result':{'ok':True}}),flush=True)"
  p=subprocess.Popen([sys.executable,'-c',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
  try:self.assertEqual(m.request(p,3,'hello',{},timeout=3),{'ok':True})
  finally:p.stdin.close();p.stdout.close();p.wait(timeout=3)
 def test_rpc_eof_is_reported(self):
  p=subprocess.Popen([sys.executable,'-c','import sys;sys.stdin.readline()'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
  try:
   with self.assertRaisesRegex(RuntimeError,'提前退出'):m.request(p,3,'hello',{},timeout=3)
  finally:p.stdin.close();p.stdout.close();p.wait(timeout=3)
