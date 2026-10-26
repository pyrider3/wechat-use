import os,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from support import installer
class InstallerTests(unittest.TestCase):
 def invoke(self,home,update=False):
  prefix=home/'install';original=pathlib.Path.is_file
  def exists(p):return True if str(p)=='/opt/wechat/wechat' else original(p)
  def run(command,**kwargs):
   if command[:2]==['uv','venv']:
    binpath=pathlib.Path(command[2])/'bin';binpath.mkdir(parents=True)
    (binpath/'python').write_text('test');(binpath/'wbox-mcp').write_text('test')
   return subprocess.CompletedProcess(command,0,stdout=b'local-test-secret')
  def model(directory,name,digest):
   directory.mkdir(parents=True,exist_ok=True);(directory/(name+'.traineddata')).write_text('test')
  args=['install.py','--prefix',str(prefix),'--no-register']+(['--update'] if update else [])
  with patch.object(sys,'argv',args),patch.object(pathlib.Path,'home',return_value=home),patch.object(pathlib.Path,'is_file',exists),patch.object(installer.shutil,'which',return_value='/usr/bin/test'),patch.object(installer.ctypes.util,'find_library',return_value='libX11.so'),patch.object(installer.subprocess,'run',side_effect=run),patch.object(installer,'ensure_model',side_effect=model),patch.dict(os.environ,{'XDG_RUNTIME_DIR':str(home/'runtime')}):
   self.assertEqual(installer.main(),0)
  return prefix
 def test_fresh_install_includes_fast_tools_and_ocr(self):
  with tempfile.TemporaryDirectory() as t:
   home=pathlib.Path(t);prefix=self.invoke(home)
   for name in ['manual-guard.py','auto_file_helper.py','wechat_regions.py','tessdata/chi_sim.traineddata','tessdata/eng.traineddata']:self.assertTrue((prefix/name).is_file())
   launcher=(home/'.local/bin/wbox-mcp').read_text();self.assertIn(str(prefix/'.venv/bin/python'),launcher)
   self.assertFalse((home/'.config/wbox-mcp/wechat/auto-layout.json').exists())
   self.assertTrue((home/'.config/wbox-mcp/wechat/auto-layout.example.json').exists())
 def test_update_preserves_account_config_credentials_and_calibration(self):
  with tempfile.TemporaryDirectory() as t:
   home=pathlib.Path(t);prefix=self.invoke(home)
   paths=[home/'.config/wbox-mcp/wechat/config.yaml',home/'.config/wbox-mcp/viewer/passwd',prefix/'wechat-profile/session-data',home/'.config/wbox-mcp/wechat/auto-layout.json',home/'.config/wbox-mcp/wechat/region-profile.json']
   for i,p in enumerate(paths):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(f'keep-{i}'.encode())
   before={p:p.read_bytes() for p in paths};self.invoke(home,True)
   self.assertEqual({p:p.read_bytes() for p in paths},before)
   self.assertTrue(any((prefix/'backups').iterdir()))
if __name__=='__main__':unittest.main()
