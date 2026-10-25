#!/usr/bin/python3
import json,os,selectors,subprocess,time
PROFILE='@INSTALL@/wechat-profile'
SINK='wbox_wechat_silent'
def run(*a):return subprocess.run(['pactl',*a],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=5)
def items(kind):
 r=run('-f','json','list',kind)
 if r.returncode:raise RuntimeError('audio server unavailable')
 return json.loads(r.stdout)
def ensure_sink():
 sinks=items('sinks')
 if not any(x['name']==SINK for x in sinks):
  r=run('load-module','module-null-sink','sink_name='+SINK,'sink_properties=device.description=Background-WeChat-Silent')
  if r.returncode:raise RuntimeError('cannot create silent sink')
 if not any(x['name']==SINK and x.get('mute') for x in sinks):run('set-sink-mute',SINK,'1')
def belongs(props):
 try:return os.path.samestat(os.stat(PROFILE),os.stat('/proc/'+str(int(props['application.process.id']))+'/root@HOME@'))
 except (KeyError,OSError,ValueError):return False
def silence():
 sinks=items('sinks');idx=next(x['index'] for x in sinks if x['name']==SINK)
 clients={str(x['index']):x.get('properties',{}) for x in items('clients')}
 for stream in items('sink-inputs'):
  props=stream.get('properties',{})
  if not (belongs(props) or belongs(clients.get(str(stream.get('client')),{}))):continue
  if not stream['mute']:run('set-sink-input-mute',str(stream['index']),'1')
  if stream['sink']!=idx:run('move-sink-input',str(stream['index']),SINK)
while True:
 sub=None
 try:
  ensure_sink();silence()
  sub=subprocess.Popen(['pactl','subscribe'],stdout=subprocess.PIPE,text=True,bufsize=1)
  sel=selectors.DefaultSelector();sel.register(sub.stdout,selectors.EVENT_READ)
  last=0
  while sub.poll() is None:
   events=sel.select(timeout=1)
   if events:sub.stdout.readline()
   now=time.monotonic()
   if events or now-last>2:
    ensure_sink();silence();last=now
 except Exception as e:
  print(str(e),flush=True);time.sleep(2)
 finally:
  if sub is not None:sub.terminate()
