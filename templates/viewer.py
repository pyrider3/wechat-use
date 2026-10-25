#!/usr/bin/python3
import fcntl,json,os,pathlib,socket,subprocess,sys,time
runtime=pathlib.Path('@RUNTIME@')
lock=(runtime/'wbox-wechat-manual.lock').open('w')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
 subprocess.run(['notify-send','后台微信','查看器已经打开，请切换到“后台微信 · 独立桌面”窗口。']);sys.exit(0)
try:
 state=json.loads(pathlib.Path('/tmp/wbox_codex-background-wechat_state.json').read_text())
 if pathlib.Path(f"/proc/{int(state['compositor_pid'])}/exe").resolve().name!='labwc':raise RuntimeError()
except Exception:
 subprocess.run(['notify-send','后台微信','独立桌面未运行，请让 Codex 通过 wbox-wechat 启动后再打开。']);sys.exit(1)
subprocess.run(['systemctl','--user','restart','wbox-wechat-viewer.service'],check=True)
for _ in range(40):
 try:
  with socket.create_connection(('127.0.0.1',15927),timeout=.2):break
 except OSError:time.sleep(.1)
else:
 subprocess.run(['notify-send','后台微信','查看服务未启动，请检查 wbox-wechat-viewer.service。']);sys.exit(1)
marker=runtime/'wbox-wechat-manual.pid'
marker.write_text(str(os.getpid()))
try:
 env=os.environ.copy()
 env['LD_LIBRARY_PATH']='@INSTALL@/runtime/usr/lib'
 subprocess.run(['@INSTALL@/runtime/usr/bin/vncviewer','-SecurityTypes','VncAuth','-PasswordFile','@HOME@/.config/wbox-mcp/viewer/passwd','-RemoteResize=0','-AcceptClipboard=0','-SendClipboard=0','-SendPrimary=0','-SetPrimary=0','127.0.0.1::15927'],env=env)
finally:marker.unlink(missing_ok=True)
