"""Optional read-only OCR element map; never sends, clicks, or changes control mode."""
import hashlib,json,time
from concurrent.futures import ThreadPoolExecutor
import auto_file_helper as auto
from wechat_regions import PROFILE,rect,signature,distance
from wechat_workflow import lines

class ElementMap:
 def __init__(self,regions):self.regions=regions;self.cache={}
 def cached(self,im,kind,read):
  key=(kind,im.size,hashlib.sha256(im.tobytes()).hexdigest())
  if key in self.cache:return self.cache[key],0
  value=read(im)
  if len(self.cache)>80:self.cache={}
  self.cache[key]=value;return value,1
 def inspect(self):
  start=time.perf_counter();r=self.regions;layout=r.check();frame=auto.image(r.capture());captured_at=time.time()
  if list(frame.size)!=layout['size']:raise ValueError('element_frame_size_changed')
  profile=json.loads(PROFILE.read_text())
  def crop(region):
   x,y,w,h=rect(region);return frame.crop((x,y,x+w,y+h))
  # Validate anchors from this exact full frame, not only earlier anchor screenshots.
  for anchor in profile['anchors']:
   if distance(signature(crop(anchor['region'])),anchor['signature'])>3:raise ValueError('element_frame_layout_changed')
  hx,_,_,_=rect(layout['header']);cx=max(110,int(hx*.36));cy=145;cw=hx-cx-25;ch=layout['size'][1]-cy-100
  contacts_region=f'{cx},{cy} {cw}x{ch}'
  header=crop(layout['header']);draft=crop(layout['draft']);contacts=crop(contacts_region);messages=crop(layout['messages']);bubble=auto.last_bubble(messages)
  with ThreadPoolExecutor(max_workers=4) as pool:
   ht=pool.submit(self.cached,header,'title',lambda im:auto.ocr(im,7))
   dt=pool.submit(self.cached,draft,'draft',lambda im:auto.ocr(im,6))
   ct=pool.submit(self.cached,contacts,'contact_rows',lines)
   bt=pool.submit(self.cached,bubble[1],'bubble',auto.message_ocr) if bubble else None
   (title,tc),hn=ht.result();(draft_text,dc),dn=dt.result();rows,cn=ct.result()
   (message,mc,method),bn=bt.result() if bt else (('',0,'none'),0)
  if not title or tc<85:raise ValueError('element_title_unverified')
  elements=[];uncertain=[]
  def add(role,text,box,confidence,source,**extra):
   x,y,w,h=box
   elements.append({'id':f'e{len(elements)+1}','role':role,'text':text,'bounds':[x,y,w,h],'center':[x+w//2,y+h//2],'confidence':confidence,'source':source,**extra})
  add('chat_title',title,rect(layout['header']),tc,'ocr')
  if 'search' in layout:add('search_field',None,layout['search']['box'],None,'reviewed_layout',note='position only; current field text/focus not inspected')
  for row in rows:
   if row['confidence']>=85:add('recent_chat_name',row['text'],[cx+row['x'],cy+row['y'],row['width'],row['height']],row['confidence'],'ocr',note='display name only; not unique-account identity')
   else:uncertain.append({'region':'contacts','reason':'low_confidence_row'})
  if draft_text and dc>=75:add('draft_text',draft_text,rect(layout['draft']),dc,'ocr')
  elif draft_text:uncertain.append({'region':'draft','reason':'low_confidence'})
  # Absence of OCR text never becomes an automatic empty-draft assertion.
  x,y=layout['input'];add('message_input',None,[x,y,1,1],None,'reviewed_layout',note='input point; use existing clipboard draft checks before sending')
  if bubble and message and mc>=75:
   mx,my,_,_=rect(layout['messages']);l,t,rr,b=bubble[0]
   add('outgoing_message',message,[mx+l,my+t,rr-l,b-t],mc,'ocr',ocr_method=method)
  elif bubble:uncertain.append({'region':'latest_outgoing','reason':'unreliable_ocr'})
  self.last_contacts=(contacts_region,hashlib.sha256(contacts.tobytes()).hexdigest())
  return {'status':'ready','mode':'experimental_read_only','frame_id':hashlib.sha256(frame.tobytes()).hexdigest()[:20],'captured_at_unix':captured_at,'viewport':layout['size'],'elements':elements,'uncertain_regions':uncertain,'image_returned':False,'ocr_cache_misses':hn+dn+cn+bn,'elapsed_ms':round((time.perf_counter()-start)*1000,2),'instruction':'Element IDs/coordinates describe this captured frame only. Prefer existing guarded send/search tools. Unknown overlays require fresh visual review; no actions are enabled by this read-only tool.'}
 def run(self):
  try:return {'content':[{'type':'text','text':json.dumps(self.inspect(),ensure_ascii=False)}]}
  except Exception as error:return self.regions.fallback(error)
