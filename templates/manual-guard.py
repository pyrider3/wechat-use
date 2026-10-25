#!/usr/bin/python3
import fcntl,json,pathlib,subprocess,sys,threading
p=subprocess.Popen(['@INSTALL@/wbox-mcp-direct',*sys.argv[1:]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
output_lock=threading.Lock()
def emit(line):
 with output_lock:sys.stdout.write(line);sys.stdout.flush()
def forward():
 for line in p.stdout:emit(line)
t=threading.Thread(target=forward,daemon=True);t.start()
observe={'screenshot','list_windows','get_size','get_mouse_position','tail_log'}
try:
 for line in sys.stdin:
  try:
   req=json.loads(line)
   if req.get('method')=='tools/call' and req.get('params',{}).get('name') not in observe:
    with open('@RUNTIME@/wbox-wechat-manual.lock','a') as lock:
     try:fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
     except BlockingIOError:
      emit(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':{'content':[{'type':'text','text':'manual_control_active: 用户正在查看器中操作后台微信。自动操作已暂停；请等用户关闭查看器后再继续。'}],'isError':True}},ensure_ascii=False)+'\n');continue
  except (ValueError,KeyError):pass
  p.stdin.write(line);p.stdin.flush()
finally:
 p.stdin.close()
 try:p.wait(timeout=3)
 except subprocess.TimeoutExpired:
  p.terminate();p.wait(timeout=3)
 t.join(timeout=2)
