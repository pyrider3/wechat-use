#!/usr/bin/python3
"""Keep the locally launched desktop owned by a user service, not an AI client."""
import fcntl,json,pathlib,selectors,subprocess,time
STATE=pathlib.Path('/tmp/wbox_codex-background-wechat_state.json')
RUNTIME=pathlib.Path('@RUNTIME@')
def running():
 try:
  s=json.loads(STATE.read_text())
  return pathlib.Path(f"/proc/{int(s['compositor_pid'])}/exe").resolve().name=='labwc'
 except (OSError,ValueError,KeyError,TypeError):return False

def request(p,number,method,params,timeout=45):
 p.stdin.write(json.dumps({'jsonrpc':'2.0','id':number,'method':method,'params':params})+'\n');p.stdin.flush()
 deadline=time.monotonic()+timeout
 # Read bytes directly: buffered text readline can hide already buffered lines
 # from select when the server sends notifications before its response.
 data=b'';selector=selectors.DefaultSelector();selector.register(p.stdout,selectors.EVENT_READ)
 try:
  while time.monotonic()<deadline:
   if not selector.select(max(0,deadline-time.monotonic())):break
   import os
   chunk=os.read(p.stdout.fileno(),65536)
   if not chunk:raise RuntimeError('后台启动进程提前退出')
   data+=chunk
   while b'\n' in data:
    line,data=data.split(b'\n',1)
    try:reply=json.loads(line)
    except ValueError:continue
    if reply.get('id')==number:
     if 'error' in reply:raise RuntimeError(str(reply['error']))
     return reply['result']
  raise RuntimeError('后台微信启动超时')
 finally:selector.close()

def serve():
 with (RUNTIME/'wbox-wechat-action.lock').open('a') as lock:
  # Same cross-process action lock used by Codex/Pi; never race their launch.
  fcntl.flock(lock,fcntl.LOCK_EX)
  if running():return
  p=subprocess.Popen(['@INSTALL@/wbox-mcp-direct','serve','--mcp-dir','@HOME@/.config/wbox-mcp/wechat'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
  try:
   request(p,1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'background-wechat-session','version':'1'}})
   p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');p.stdin.flush()
   result=request(p,2,'tools/call',{'name':'launch','arguments':{}})
   if result.get('isError') or not running():raise RuntimeError('后台微信未成功启动: '+str(result.get('content')))
  except BaseException:
   p.terminate();p.wait(timeout=10);raise
  finally:fcntl.flock(lock,fcntl.LOCK_UN)
 # Keep stdin open: exiting the owning MCP server stops its compositor.
 try:
  while p.poll() is None and running():time.sleep(.5)
 finally:
  if p.poll() is None:p.terminate();p.wait(timeout=10)
 if p.returncode:raise SystemExit(p.returncode)
if __name__=='__main__':serve()
