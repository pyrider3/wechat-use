"""Region-based WeChat state reader. Full images are returned only for calibration/fallback."""
import base64,ctypes as C,hashlib,io,json,os,pathlib,re,time
from concurrent.futures import ThreadPoolExecutor
from PIL import Image,ImageChops
import auto_file_helper as auto
PROFILE=pathlib.Path.home()/'.config/wbox-mcp/wechat/region-profile.json'
class LayoutError(RuntimeError):pass
class Attr(C.Structure):
 _fields_=[(n,t) for n,t in [('x',C.c_int),('y',C.c_int),('width',C.c_int),('height',C.c_int),('border_width',C.c_int),('depth',C.c_int),('visual',C.c_void_p),('root',C.c_ulong),('klass',C.c_int),('bit_gravity',C.c_int),('win_gravity',C.c_int),('backing_store',C.c_int),('backing_planes',C.c_ulong),('backing_pixel',C.c_ulong),('save_under',C.c_int),('colormap',C.c_ulong),('map_installed',C.c_int),('map_state',C.c_int),('all_event_masks',C.c_long),('your_event_mask',C.c_long),('do_not_propagate_mask',C.c_long),('override_redirect',C.c_int),('screen',C.c_void_p)]]
def inventory():
 state=json.loads(pathlib.Path('/tmp/wbox_codex-background-wechat_state.json').read_text())
 lib=C.CDLL('libX11.so.6');lib.XOpenDisplay.argtypes=[C.c_char_p];lib.XOpenDisplay.restype=C.c_void_p
 d=lib.XOpenDisplay(state['x_display'].encode())
 if not d:raise LayoutError('display_unavailable')
 lib.XDefaultRootWindow.argtypes=[C.c_void_p];lib.XDefaultRootWindow.restype=C.c_ulong
 lib.XQueryTree.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]
 lib.XGetWindowAttributes.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(Attr)]
 lib.XFree.argtypes=[C.c_void_p];lib.XCloseDisplay.argtypes=[C.c_void_p]
 lib.XDisplayWidth.argtypes=[C.c_void_p,C.c_int];lib.XDisplayHeight.argtypes=[C.c_void_p,C.c_int]
 # Ignore windows disappearing between enumeration and attribute read.
 callback=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p)(lambda *_:0)
 lib.XSetErrorHandler.argtypes=[C.c_void_p];lib.XSetErrorHandler.restype=C.c_void_p;previous=lib.XSetErrorHandler(C.cast(callback,C.c_void_p))
 try:
  root=lib.XDefaultRootWindow(d);r=C.c_ulong();parent=C.c_ulong();children=C.POINTER(C.c_ulong)();count=C.c_uint()
  lib.XQueryTree(d,root,C.byref(r),C.byref(parent),C.byref(children),C.byref(count));visible=[]
  for i in range(min(count.value,1000)):
   a=Attr()
   if lib.XGetWindowAttributes(d,children[i],C.byref(a)) and a.map_state==2 and a.width>8 and a.height>8:
    visible.append({'id':int(children[i]),'x':a.x,'y':a.y,'width':a.width,'height':a.height,'override_redirect':bool(a.override_redirect)})
  if children:lib.XFree(children)
  return {'size':[lib.XDisplayWidth(d,0),lib.XDisplayHeight(d,0)],'windows':visible}
 finally:
  lib.XCloseDisplay(d);lib.XSetErrorHandler(previous)
def rect(s):
 m=re.fullmatch(r'(\d+),(\d+) (\d+)x(\d+)',s)
 if not m:raise ValueError('invalid rectangle')
 x,y,w,h=map(int,m.groups())
 if w<1 or h<1:raise ValueError('empty rectangle')
 return x,y,w,h
def signature(im):
 im=im.convert('L').resize((80,12));return list(im.tobytes())
def distance(a,b):return sum(abs(x-y) for x,y in zip(a,b))/len(a)
class Regions:
 def __init__(self,proxy):self.proxy=proxy;self.cache={};self.captures=0;self.full_frames=0;self.ocr_calls=0
 def capture(self,region=None):
  self.captures+=1;self.full_frames+=region is None
  return self.proxy.call('screenshot',{'region':region} if region else {})
 def im(self,region=None):return auto.image(self.capture(region))
 def recognize(self,im,psm=7):
  key=(hashlib.sha256(im.tobytes()).hexdigest(),im.size,psm)
  if key not in self.cache:
   self.ocr_calls+=1;self.cache[key]=auto.ocr(im,psm)
   if len(self.cache)>80:self.cache={key:self.cache[key]}
  return self.cache[key]
 def recognize_message(self,im):
  key=(hashlib.sha256(im.tobytes()).hexdigest(),im.size,'message')
  if key not in self.cache:
   words,confidence,method=auto.message_ocr(im)
   self.ocr_calls+=1 if method=='original' else 4
   if len(self.cache)>80:self.cache={}
   self.cache[key]=(words,confidence)
  return self.cache[key]
 def calibrate(self,layout=None):
  inv=inventory();self.proxy.focus()
  if len(inv['windows'])!=1 or inv['windows'][0]['override_redirect']:raise LayoutError('popup_or_extra_window')
  if layout is None and not auto.LAYOUT.exists():raise LayoutError('needs_layout: infer regions from the fresh full screenshot and pass layout to calibrate_regions')
  layout=layout or json.loads(auto.LAYOUT.read_text())
  if layout['size']!=inv['size']:raise LayoutError('layout_changed: provide regions derived from the returned full screenshot')
  full=self.capture();im=auto.image(full)
  if list(im.size)!=layout['size']:raise LayoutError('frame_size_mismatch')
  W,H=im.size
  if not isinstance(layout.get('input'),list) or len(layout['input'])!=2 or any(not isinstance(v,int) for v in layout['input']) or not (0<=layout['input'][0]<W and 0<=layout['input'][1]<H):raise ValueError('invalid input coordinate')
  for name in ['header','messages','draft']:
   x,y,w,h=rect(layout[name])
   if x+w>W or y+h>H:raise ValueError('rectangle outside screen')
  # Stable separators / toolbar areas: never use dynamic conversation pixels as anchors.
  x,y,w,h=rect(layout['draft']);hx,hy,hw,hh=rect(layout['header'])
  # The old H-72 strip could include draft text/caret in tall layouts.
  # Explicit reviewed strips allow the host to choose actual static separators.
  anchors=layout.get('anchor_regions') or [f'{hx},{hy+hh+9} {min(W-hx-10,700)}x8',f'{max(0,x-10)},{max(0,y-25)} {min(W-x,680)}x7']
  if not isinstance(anchors,list) or not 2<=len(anchors)<=6 or any(not isinstance(a,str) for a in anchors) or len(set(anchors))!=len(anchors):raise ValueError('need 2-6 reviewed static anchor strips')
  ref=[]
  for region in anchors:
   rx,ry,rw,rh=rect(region)
   if rx+rw>W or ry+rh>H:raise ValueError('anchor outside screen')
   for content in ('header','messages','draft'):
    cx,cy,cw,ch=rect(layout[content])
    if rx<cx+cw and cx<rx+rw and ry<cy+ch and cy<ry+rh:raise ValueError('anchor overlaps dynamic '+content)
   if rh>12 and rw>12:raise ValueError('anchors must be narrow static strips')
   ref.append({'region':region,'signature':signature(im.crop((rx,ry,rx+rw,ry+rh)))})
  profile={'layout':layout,'anchors':ref,'geometry':{k:inv['windows'][0][k] for k in ['x','y','width','height']},'created':time.time(),'anchor_version':2}
  PROFILE.parent.mkdir(parents=True,exist_ok=True);tmp=PROFILE.with_suffix('.tmp');tmp.write_text(json.dumps(profile));tmp.chmod(0o600);os.replace(tmp,PROFILE)
  # Explicitly reviewed calibration is shared with both automatic send paths.
  layout_tmp=auto.LAYOUT.with_suffix('.tmp');layout_tmp.write_text(json.dumps(layout));layout_tmp.chmod(0o600);os.replace(layout_tmp,auto.LAYOUT)
  self.cache={}
  return full
 def check(self):
  if not PROFILE.exists():raise LayoutError('needs_calibration')
  profile=json.loads(PROFILE.read_text());self.layout=profile['layout'];inv=inventory();self.proxy.focus()
  if inv['size']!=self.layout['size']:raise LayoutError('layout_changed: screen size differs')
  if len(inv['windows'])!=1 or inv['windows'][0]['override_redirect']:raise LayoutError('popup_or_extra_window')
  if {k:inv['windows'][0][k] for k in profile['geometry']}!=profile['geometry']:raise LayoutError('layout_changed: window moved or resized')
  failed=[]
  for index,anchor in enumerate(profile['anchors']):
   delta=distance(signature(self.im(anchor['region'])),anchor['signature'])
   if delta>3.0:failed.append({'index':index,'region':anchor['region'],'difference':round(delta,2)})
  if failed:
   # One observation-only retry handles compositor repaint. Never update baselines.
   time.sleep(.12);fresh=inventory();self.proxy.focus()
   if fresh['size']!=inv['size'] or fresh['windows']!=inv['windows']:raise LayoutError('layout_changed_during_recheck: inspect fresh screenshot')
   failed=[{**a,'difference':round(distance(signature(self.im(a['region'])),profile['anchors'][a['index']]['signature']),2)} for a in failed]
   failed=[a for a in failed if a['difference']>3.0]
   if failed:raise LayoutError('anchor_review_required: '+json.dumps({'failed':failed,'anchor_version':profile.get('anchor_version',1)}))
  return self.layout
 def header(self):return self.recognize(self.im(self.layout['header']))
 def inspect(self,contacts=False):
  start=time.perf_counter();c0,o0,f0=self.captures,self.ocr_calls,self.full_frames
  self.check()
  header_im=self.im(self.layout['header']);messages=self.im(self.layout['messages']);draft=self.im(self.layout['draft'])
  bubble=auto.last_bubble(messages)
  with ThreadPoolExecutor(max_workers=3) as pool:
   title_task=pool.submit(self.recognize,header_im,7);draft_task=pool.submit(self.recognize,draft,6)
   message_task=pool.submit(self.recognize_message,bubble[1]) if bubble else None
   title,tc=title_task.result();draft_text,dc=draft_task.result();latest,mc=message_task.result() if message_task else ('',0)
  if not title or tc<70:raise LayoutError('title_unreadable')
  result={'status':'ready','chat':title,'chat_confidence':tc,'draft_ocr':draft_text,'latest_outgoing_ocr':latest if mc>=75 else None,'latest_outgoing_confidence':mc,'latest_outgoing_reliable':bool(latest and mc>=75),'popup':False,'layout':'valid'}
  if contacts:
   hx,_,_,_=rect(self.layout['header']);region=f'115,145 {max(80,hx-125)}x{min(600,self.layout["size"][1]-230)}'
   words,confidence=self.recognize(self.im(region),6)
   result['contact_list_ocr']=words if confidence>=75 else None
   result['contacts_confidence']=confidence
   result['contacts_reliable']=confidence>=75
  result['elapsed_ms']=round((time.perf_counter()-start)*1000,2);result['captures']=self.captures-c0;result['full_frames']=self.full_frames-f0;result['ocr_calls']=self.ocr_calls-o0
  return result
 def fallback(self,error):
  result=self.capture();reason=str(error)
  recoverable=('SEND_UNCERTAIN' not in reason and (reason.startswith('layout_changed:') or reason=='needs_calibration'))
  data={'status':'layout_recalibration_required' if recoverable else 'needs_visual_review','reason':reason,'action':'Inspect this fresh full screenshot. Do not send using the cached layout; recalibrate only from the new image.'}
  if reason.startswith('anchor_review_required:'):
   data.update({'status':'anchor_review_required','instruction':'Inspect the returned fresh image. Geometry has not changed: do NOT automatically recalibrate or repeat the same check. If a menu/dialog obscures the window, dismiss only task-appropriate overlays then check once. If the image proves normal content/caret overlaps a failed anchor, call calibrate_regions with the existing verified layout plus 2-6 visually reviewed anchor_regions on static narrow separators OUTSIDE header/messages/draft, then verify inspect_regions and resume original workflow/operation_ids. Never accept an overlay as a new baseline or lower thresholds. Unknown obstruction needs visual resolution, not blind calibration.'})
  if recoverable:
   try:data['actual_size']=list(auto.image(result).size)
   except Exception:data['actual_size']=None
   try:data['windows']=inventory()['windows']
   except Exception:data['windows']=None
   data.update({'next_tool':'calibrate_regions','preserve_user_resolution':True,'instruction':'Recover within this task: inspect this image, derive NEW header/messages/draft/input and search regions from actual window pixels, then call calibrate_regions with explicit layout. Never resize the display back, scale old coordinates blindly, or switch the whole batch to step-by-step screenshots. Verify inspect_regions after calibration, then continue the original workflow with unchanged operation_ids. Popup/obscured/ambiguous layout must be resolved before calibration. Do not include stale search/group/forward sub-layouts: recalibrate each from pixels before using it. Already submitted/uncertain messages are observe-only.'})
  result['isError']=True;result['content'].insert(0,{'type':'text','text':json.dumps(data,ensure_ascii=False)});return result
 def run(self,name,args):
  try:
   if name=='calibrate_regions':
    frame=self.calibrate(args.get('layout'));frame['content'].insert(0,{'type':'text','text':'Layout calibrated from a fresh full frame. Confirm these regions before automatic actions.'});return frame
   if name=='inspect_regions':return {'content':[{'type':'text','text':json.dumps(self.inspect(args.get('contacts',False)),ensure_ascii=False)}]}
   if not PROFILE.exists():raise LayoutError('needs_calibration')
   self.check()
   return auto.send(self.proxy,args,regions=self,recipient=args.get("recipient","") if name=="send_partitioned_to_contact" else "文件传输助手")
  except Exception as error:
   from wechat_visual import eligible,prepare
   if name=='send_partitioned_to_contact' and eligible(error):
    try:return prepare(self,args,reason=str(error))
    except Exception as review_error:return self.fallback(review_error)
   return self.fallback(error)
