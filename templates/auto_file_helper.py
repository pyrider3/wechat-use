"""Conservative OCR fast path for an explicitly named, already-open chat."""
import base64,csv,hashlib,io,json,os,pathlib,re,secrets,subprocess,time,unicodedata
from PIL import Image,ImageChops,ImageOps
BASE=pathlib.Path(__file__).resolve().parent
STATE=pathlib.Path.home()/'.local/state/wbox-wechat/auto-send'
LAYOUT=pathlib.Path.home()/'.config/wbox-mcp/wechat/auto-layout.json'
def norm(text):return ''.join(unicodedata.normalize('NFKC',text).split())
def png(result):return base64.b64decode(next(c['data'] for c in result['content'] if c['type']=='image'))
def image(result):return Image.open(io.BytesIO(png(result))).convert('RGB')
def ocr(im,psm=7):
 b=io.BytesIO();im.save(b,format='PNG')
 r=subprocess.run(['tesseract','stdin','stdout','--tessdata-dir',str(BASE/'tessdata'),'-l','chi_sim+eng','--psm',str(psm),'-c','tessedit_create_tsv=1'],input=b.getvalue(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,check=True)
 rows=[r for r in csv.DictReader(io.StringIO(r.stdout.decode()),delimiter='\t',quoting=csv.QUOTE_NONE) if r.get('text','').strip() and float(r['conf'])>=0]
 return ''.join(r['text'] for r in rows),min((float(r['conf']) for r in rows),default=0)
def message_ocr(im):
 # No expected-text hints, dictionary substitution, or lower acceptance threshold.
 words,confidence=ocr(im,6)
 if confidence>=75:return words,confidence,'original'
 observations=[(words,confidence)]
 for threshold in (130,100,170):
  mask=im.convert('L').point([0 if v<threshold else 255 for v in range(256)]).convert('RGB')
  observations.append(ocr(ImageOps.expand(mask,border=12,fill='white'),6))
 high=[(w,c) for w,c in observations if w and c>=75]
 keys={norm(w) for w,c in high}
 if len(keys)==1:
  agreed=next(iter(keys))
  # Either original + a high-confidence view, or two high-confidence white views.
  original_support=bool(words and confidence>=50 and norm(words)==agreed)
  if original_support or len(high)>=2:
   selected=max(high,key=lambda item:item[1])
   return selected[0],selected[1],'multiview_agreement'
 return words,min(confidence,74.99),'unresolved'
def last_bubble(im):
 # Only green outgoing bubbles; ignore incoming white bubbles and timestamps.
 r,g,b=im.split()
 mask=ImageChops.multiply(r.point([255 if 105<=i<=210 else 0 for i in range(256)]),g.point([255 if i>=205 else 0 for i in range(256)]))
 mask=ImageChops.multiply(mask,b.point([255 if 90<=i<=205 else 0 for i in range(256)]))
 mask=ImageChops.multiply(mask,ImageChops.subtract(g,r).point([255 if i>=25 else 0 for i in range(256)]))
 rows=[]
 for y in range(im.height):
  row=mask.crop((0,y,im.width,y+1));box=row.getbbox()
  if box and row.histogram()[255]>=40:rows.append((y,box[0],box[2]-1))
 if not rows:return None
 groups=[]
 for row in rows:
  if not groups or row[0]-groups[-1][-1][0]>2:groups.append([])
  groups[-1].append(row)
 groups=[g for g in groups if g[-1][0]-g[0][0]>=18]
 if not groups:return None
 g=groups[-1];box=(min(r[1] for r in g),g[0][0],max(r[2] for r in g)+1,g[-1][0]+1)
 return box,im.crop((box[0]+8,box[1]+5,box[2]-12,box[3]-5))
def copy_draft(proxy):
 marker='empty-probe-'+secrets.token_hex(12)
 proxy.call('clipboard_write',{'text':marker});proxy.call('key',{'shortcut':'ctrl+a'});proxy.call('key',{'shortcut':'ctrl+c'});time.sleep(.03)
 r=proxy.call('clipboard_read',{});text=next(c['text'] for c in r['content'] if c['type']=='text')
 proxy.call('key',{'shortcut':'ctrl+End'})
 return '' if text==marker else text
def send(proxy,args,regions=None,recipient="文件传输助手",visual_guard=None):
 if not isinstance(recipient,str) or not recipient.strip() or len(recipient)>80 or any(ord(c)<32 for c in recipient):raise ValueError("invalid_recipient")
 recipient=unicodedata.normalize("NFC",recipient)
 recipient_hash=hashlib.sha256(recipient.encode()).hexdigest()
 started=time.perf_counter();text=args.get('text');op=args.get('operation_id','')
 if not isinstance(text,str) or not 1<=len(text)<=80 or any(ord(c)<32 for c in text):raise ValueError('Only single-line text up to 80 characters is supported')
 if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',op):raise ValueError('operation_id must be a unique 8-80 character identifier')
 layout=json.loads(LAYOUT.read_text());STATE.mkdir(parents=True,exist_ok=True);STATE.chmod(0o700)
 path=STATE/(hashlib.sha256(op.encode()).hexdigest()+'.json');digest=hashlib.sha256(text.encode()).hexdigest()
 if path.exists():
  previous=json.loads(path.read_text())
  if previous.get('recipient_hash',hashlib.sha256('文件传输助手'.encode()).hexdigest())!=recipient_hash:raise ValueError('operation_id reused with different recipient')
  if previous['text_hash']!=digest:raise ValueError('operation_id reused with different text')
  return {'content':[{'type':'text','text':json.dumps({'duplicate_request':True,**previous})}],'isError':previous.get('status')!='ui_confirmed'}
 def save(status,**fields):
  record={'status':status,'text_hash':digest,'recipient_hash':recipient_hash,**fields};tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(record));tmp.chmod(0o600);os.replace(tmp,path);return record
 # All mutations are already serialized by the proxy's manual and automation locks.
 sending=False
 try:
  focus=proxy.focus()
  if regions:
   layout=regions.check()
  else:
   full=proxy.call('screenshot',{});im=image(full)
   if list(im.size)!=layout['size']:raise ValueError('layout_changed: recalibrate from a fresh screenshot')
  def header():
   if visual_guard is not None:
    visual_guard();return
   if regions:
    regions.check();words,confidence=regions.header()
   else:words,confidence=ocr(image(proxy.call('screenshot',{'region':layout['header']})))
   if unicodedata.normalize('NFC',words)!=recipient or confidence<85:raise ValueError('recipient_unverified: exact expected chat title not confidently recognized')
  header()
  before=last_bubble(image(proxy.call('screenshot',{'region':layout['messages']})))
  if before and norm(ocr(before[1],6)[0])==norm(text):raise ValueError('same_last_message: inspect instead of possibly resending')
  proxy.call('click',{'x':layout['input'][0],'y':layout['input'][1]})
  existing=copy_draft(proxy)
  if existing and not (visual_guard is not None and existing==text):raise ValueError('draft_not_empty: nothing replaced or sent')
  if not existing:
   proxy.call('clipboard_write',{'text':text});proxy.call('key',{'shortcut':'ctrl+v'});time.sleep(.08)
  if copy_draft(proxy)!=text:raise ValueError('draft_mismatch: nothing sent; inspect draft')
  proxy.call('clipboard_write',{'text':text})
  if proxy.focus()!=focus:raise ValueError('focus_changed: nothing sent')
  header();save('sending');sending=True
  proxy.call('key',{'shortcut':'Return'})
  bubble_cache={}
  # Observe only after Enter; never submit again during verification.
  for attempt in range(3):
   time.sleep(.2)
   if proxy.focus()!=focus:continue
   panel=image(proxy.call('screenshot',{'region':layout['messages']}));bubble=last_bubble(panel)
   if not bubble:continue
   box,crop=bubble;cache_key=(crop.size,hashlib.sha256(crop.tobytes()).hexdigest())
   if cache_key not in bubble_cache:bubble_cache[cache_key]=message_ocr(crop)
   words,confidence,ocr_method=bubble_cache[cache_key]
   if norm(words)!=norm(text) or confidence<75:continue
   left=max(0,box[0]-55);near=panel.crop((left,max(0,box[1]-5),box[2],min(panel.height,box[3]+5)))
   if any(r>180 and g<105 and b<105 for r,g,b in near.getdata()):continue
   proxy.call('click',{'x':layout['input'][0],'y':layout['input'][1]})
   if copy_draft(proxy):continue
   draft_words,_=ocr(image(proxy.call('screenshot',{'region':layout['draft']})),6)
   if norm(draft_words):continue
   header()
   record=save('ui_confirmed',recipient=recipient,outgoing_bubble_matched=True,message_ocr_method=ocr_method,message_ocr_confidence=confidence,input_empty=True,no_failure_marker_seen=True,elapsed_ms=round((time.perf_counter()-started)*1000,2))
   result={'content':[]} if regions else proxy.call('screenshot',{});result['content'].insert(0,{'type':'text','text':json.dumps(record,ensure_ascii=False)});return result
  raise RuntimeError('outgoing message or empty input could not be verified')
 except Exception as e:
  if sending:
   save('send_uncertain');raise RuntimeError('SEND_UNCERTAIN: Enter may already have been dispatched; inspect, never retry automatically. '+str(e))
  raise
