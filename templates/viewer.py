#!/usr/bin/python3
import fcntl,json,os,pathlib,socket,subprocess,sys,time,shutil
runtime=pathlib.Path('@RUNTIME@')
def main():
 with (runtime/'wbox-wechat-viewer-instance.lock').open('w') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:
   subprocess.run(['notify-send','后台微信','查看器已经打开，请切换到“后台微信 · 独立桌面”窗口。']);sys.exit(0)
  sys.path.insert(0,'@INSTALL@')
  from session import running
  if not running():
   subprocess.run(['notify-send','后台微信','正在启动独立桌面，请稍候……'])
   try:
    subprocess.run(['systemctl','--user','start','wbox-wechat-session.service'],check=True,timeout=10)
    for _ in range(300):
     if running():break
     time.sleep(.1)
    else:raise RuntimeError('启动超时，可查看 journalctl --user -u wbox-wechat-session.service')
   except Exception as error:
    subprocess.run(['notify-send','后台微信','无法启动独立桌面：'+str(error)]);sys.exit(1)
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
   # Native per-monitor scaling; do not inherit a forced toolkit scale.
   for key in ('LD_LIBRARY_PATH','GDK_SCALE','GDK_DPI_SCALE'):env.pop(key,None)
   env['GDK_BACKEND']='wayland'
   subprocess.run(['/usr/bin/python3','@INSTALL@/scaled-viewer.py'],env=env,check=True)
  finally:marker.unlink(missing_ok=True)

if __name__=='__main__':main()
