import fcntl,importlib.util,json,os,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installer',ROOT/'install.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
class ConfigurationTests(unittest.TestCase):
 def test_rendered_programs(self):
  for p in (ROOT/'templates').iterdir():
   if not p.is_file():continue
   rendered=installer.render(p.read_text(),'/tmp/example-user','/tmp/example-install','/tmp/example-runtime')
   self.assertNotIn('@HOME@',rendered);self.assertNotIn('@INSTALL@',rendered);self.assertNotIn('@RUNTIME@',rendered)
   if p.suffix=='.py':compile(rendered,str(p),'exec')
   if p.suffix=='.sh':subprocess.run(['sh','-n'],input=rendered,text=True,check=True)
 def test_viewer_does_not_block_input_or_observation(self):
  with tempfile.TemporaryDirectory() as t:
   base=pathlib.Path(t);runtime=base/'runtime';runtime.mkdir()
   fake=base/'wbox-mcp-direct';fake.write_text('#!/usr/bin/python3\nimport sys,json\nfor line in sys.stdin:\n r=json.loads(line);print(json.dumps({"jsonrpc":"2.0","id":r["id"],"result":{"content":[{"type":"text","text":"forwarded"}]}}),flush=True)\n');fake.chmod(0o700)
   script=base/'guard.py';script.write_text(installer.render((ROOT/'templates/manual-guard.py').read_text(),base,base,runtime))
   with (runtime/'wbox-wechat-manual.lock').open('w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    requests=[{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'key'}},{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'screenshot'}}]
    # Keep stdin open until both responses arrive so the proxy can drain the upstream.
    p=subprocess.Popen(['python3',str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,env={**os.environ,'XDG_RUNTIME_DIR':str(runtime)})
    try:
     for r in requests:p.stdin.write(json.dumps(r)+'\n')
     p.stdin.flush();results={}
     for _ in requests:
      r=json.loads(p.stdout.readline());results[r['id']]=r['result']
     self.assertFalse(results[1].get('isError'));self.assertEqual(results[1]['content'][0]['text'],'forwarded')
     self.assertEqual(results[2]['content'][0]['text'],'forwarded')
    finally:p.stdin.close();p.wait(timeout=5);p.stdout.close()
if __name__=='__main__':unittest.main()
