import pathlib,tempfile,unittest,runpy,types,sys,fcntl
from unittest.mock import patch,Mock
from test_configuration import installer,ROOT
class ViewerAutostartTests(unittest.TestCase):
 def run_viewer(self,folder,running):
  base=pathlib.Path(folder);runtime=base/'runtime';runtime.mkdir(exist_ok=True)
  script=base/'viewer.py';script.write_text(installer.render((ROOT/'templates/viewer.py').read_text(),base,base,runtime));connection=Mock();connection.__enter__=Mock();connection.__exit__=Mock()
  with patch.dict(sys.modules,{'session':types.SimpleNamespace(running=Mock(side_effect=running))}),patch('subprocess.run',return_value=Mock(returncode=0)) as run,patch('socket.create_connection',return_value=connection),patch('shutil.which',return_value='/fake/vncviewer'):
   runpy.run_path(str(script),run_name='__main__')
  self.assertFalse((runtime/'wbox-wechat-manual.pid').exists());return [c.args[0] for c in run.call_args_list]
 def test_cold_start_then_viewer(self):
  with tempfile.TemporaryDirectory() as t:calls=self.run_viewer(t,[False,True])
  self.assertTrue(any(c[:4]==['systemctl','--user','start','wbox-wechat-session.service'] for c in calls));self.assertEqual(calls[-1][0],'/fake/vncviewer');self.assertIn('-RemoteResize=1',calls[-1]);self.assertIn('-PreferredEncoding=ZRLE',calls[-1]);self.assertFalse(any('stop' in c for c in calls))
 def test_warm_start_reuses_desktop(self):
  with tempfile.TemporaryDirectory() as t:calls=self.run_viewer(t,[True])
  self.assertFalse(any(c[:3]==['systemctl','--user','start'] for c in calls));self.assertEqual(calls[-1][0],'/fake/vncviewer');self.assertIn('-RemoteResize=1',calls[-1]);self.assertIn('-PreferredEncoding=ZRLE',calls[-1])
 def test_duplicate_click_does_not_launch_again(self):
  with tempfile.TemporaryDirectory() as t:
   runtime=pathlib.Path(t)/'runtime';runtime.mkdir()
   with (runtime/'wbox-wechat-viewer-instance.lock').open('w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with patch('subprocess.run') as run:
     with self.assertRaises(SystemExit) as error:self.run_viewer(t,[False])
    self.assertEqual(error.exception.code,0)
