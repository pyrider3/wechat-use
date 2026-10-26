"""Guarded two-text forwarding workflow. Dry runs never click the submit button."""
import hashlib,json,os,pathlib,re,secrets,time
from PIL import Image,ImageDraw
import auto_file_helper as auto
from wechat_groups import LocalOCR
from wechat_regions import PROFILE,inventory,rect
from wechat_search import region,focused,popup_check,select as open_contact
STATE=pathlib.Path.home()/'.local/state/wbox-wechat/forward-send'
SOURCE='文件传输助手'

def norm(s):return auto.norm(s)
def text_rows(rows,label,box=None):
 result=[]
 for r in rows:
  x,y,w,h=r['bounds']
  if norm(r['text'])==norm(label) and r['confidence']>=.9 and (box is None or box[0]<=x+w/2<=box[0]+box[2] and box[1]<=y+h/2<=box[1]+box[3]):result.append(r)
 return result

def unique(rows,label,box=None):
 matches=text_rows(rows,label,box)
 if len(matches)!=1:raise ValueError('forward_element_missing_or_ambiguous: '+label)
 return matches[0]

def selected_names(rows,expected):
 names=[r['text'] for r in rows if r['text'].strip()]
 if any(r['confidence']<.9 for r in rows) or sorted(names)!=sorted(expected):raise ValueError('forward_selected_recipients_mismatch')
 return names

def fingerprint(messages,recipients):
 return hashlib.sha256(json.dumps({'source':SOURCE,'messages':messages,'recipients':sorted(recipients)},ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def known_forward(messages,recipients):
 if not STATE.exists():return None
 for p in STATE.glob('*.json'):
  try:r=json.loads(p.read_text())
  except (ValueError,OSError):continue
  if r.get('status') not in {'sending','ui_confirmed','send_uncertain'}:continue
  if [norm(s) for s in r.get('source_messages',[])]==[norm(s) for s in messages] and set(r.get('recipients',[])) & set(recipients):return r
 return None

def preview_matches(rows,messages):
 if not any(SOURCE in r['text'] and '聊天记录' in r['text'] and r['confidence']>=.9 for r in rows):raise ValueError('forward_preview_source_mismatch')
 candidates=sorted([r for r in rows if norm(r['text']) in {norm(x) for x in messages} and r['confidence']>=.9 and r['bounds'][1]>140],key=lambda r:r['bounds'][1])
 if [norm(r['text']) for r in candidates]!=[norm(x) for x in messages]:raise ValueError('forward_preview_messages_mismatch')

def outgoing_two(panel,ocr,strict=False,fast=False):
 original=panel;found=[]
 for _ in range(2):
  bubble=auto.last_bubble(panel)
  if not bubble:raise ValueError('forward_requires_two_visible_outgoing_text_bubbles')
  box,crop=bubble
  text,confidence,_=auto.message_ocr(crop) if fast else ('',0,'none')
  if confidence<75:
   rows=ocr.read(crop)
   if len(rows)!=1 or rows[0]['confidence']<.9:raise ValueError('forward_source_text_unreliable_or_multiline')
   text=rows[0]['text']
  if not text or len(text)>40 or any(ord(c)<32 for c in text):raise ValueError('forward_only_short_plain_single_line_text_supported')
  found.insert(0,{'text':text,'box':box});panel=panel.crop((0,0,panel.width,box[1]))
 if strict:
  # Reject cards/photos/incoming text below the older selected message, not just skip them.
  start=found[0]['box'][1];body=original.crop((0,start,min(610,original.width),original.height)).convert('RGB');draw=ImageDraw.Draw(body)
  for item in found:
   l,t,r,b=item['box'];draw.rectangle((max(0,l-4),max(0,t-start-4),r+4,b-start+4),fill=(250,250,250))
  for r in ocr.read(original):
   x,y,w,h=r['bounds']
   if y<start or x>=610:continue
   if any(item['box'][0]-5<=x+w/2<=item['box'][2]+5 and item['box'][1]-5<=y+h/2<=item['box'][3]+5 for item in found):continue
   if re.fullmatch(r'(\d{1,2}:\d{2}|\d{4}年\d{1,2}月\d{1,2}日.*|今天.*|昨天.*)',norm(r['text'])):
    draw.rectangle((x-3,y-start-3,x+w+3,y-start+h+3),fill=(250,250,250))
   else:raise ValueError('forward_unrecognized_content_after_source_messages')
  raw=body.tobytes();unmasked=sum(1 for i in range(0,len(raw),3) if min(raw[i:i+3])<225)
  if unmasked>80:raise ValueError('forward_unknown_media_or_content: visual review required')
 return found

class Forwarder:
 def __init__(self,regions):self.r=regions;self.ocr=None;self.layout=None;self.profile=None;self.f=None;self.stages={}
 def guard(self):
  self.r.proxy.focus();inv=inventory()
  if inv['size']!=self.layout['size']:raise ValueError('forward_screen_changed')
  main=[w for w in inv['windows'] if not w['override_redirect'] and all(w[k]==v for k,v in self.profile['geometry'].items())]
  if len(main)!=1 or len(inv['windows'])>3:raise ValueError('forward_unexpected_windows')
  for w in inv['windows']:
   if w['x']+w['width']<0 or w['y']+w['height']<0 or w['x']>inv['size'][0] or w['y']>inv['size'][1]:raise ValueError('forward_window_outside_viewport')
 def capture(self):
  self.guard();return auto.image(self.r.capture())
 def crop(self,im,box):
  x,y,w,h=box;return im.crop((x,y,x+w,y+h))
 def read(self,im,box=None):return self.ocr.read(self.crop(im,box) if box else im)
 def click(self,x,y):self.guard();self.r.proxy.call('click',{'x':round(x),'y':round(y)})
 def click_label(self,label,box=None):
  im=self.capture()
  if box is None and label=='多选':
   inv=inventory();windows=[w for w in inv['windows'] if not all(w[k]==v for k,v in self.profile['geometry'].items())]
   if len(windows)!=1:raise ValueError('forward_context_menu_window_unverified')
   w=windows[0];x=max(0,w['x']);y=max(0,w['y']);box=[x,y,min(im.width,w['x']+w['width'])-x,min(im.height,w['y']+w['height'])-y]
  rows=self.read(im,box);row=unique(rows,label);x,y,w,h=row['bounds']
  if box:x+=box[0];y+=box[1]
  self.click(x+w/2,y+h/2)
 def wait(self,test,seconds=4):
  deadline=time.perf_counter()+seconds;last=None
  while time.perf_counter()<deadline:
   time.sleep(.08)
   try:
    im=self.capture();return test(im)
   except (ValueError,RuntimeError) as e:last=e
  raise ValueError('forward_wait_timeout: '+str(last))
 def wait_normal(self):
  deadline=time.perf_counter()+5;last=None
  while time.perf_counter()<deadline:
   time.sleep(.1)
   try:return self.r.check()
   except RuntimeError as e:last=e
  raise ValueError('forward_not_normal_after_action: '+str(last))
 def header_verified(self,expected,im=None):
  words,confidence=self.r.header() if im is None else auto.ocr(self.crop(im,list(rect(self.layout['header']))),7)
  if words==expected and confidence>=85:return confidence
  if im is None:im=self.capture()
  row=unique(self.read(im,list(rect(self.layout['header']))),expected);return row['confidence']
 def type_query(self,text,box):
  # Do not overwrite the clipboard with a probe while Ctrl+V may still be queued.
  for attempt in range(2):
   if not focused(self.crop(self.capture(),box)):raise ValueError('forward_query_field_not_focused')
   self.r.proxy.call('key',{'shortcut':'ctrl+a'});self.r.proxy.call('clipboard_write',{'text':text});self.r.proxy.call('key',{'shortcut':'ctrl+v'})
   def visible(im):
    x,y,w,h=box;crop=self.crop(im,[x+45,y+3,w-100,h-6]).convert('RGB');data=bytearray(crop.tobytes())
    for i in range(0,len(data),3):
     if data[i+1]>120 and data[i]<90 and data[i+2]<180 and data[i+1]-data[i]>50:data[i:i+3]=bytes([250,250,250])
    crop=Image.frombytes('RGB',crop.size,bytes(data));words,confidence=auto.ocr(crop,7)
    if words==text and confidence>=85:return True
    matches=text_rows(self.ocr.read(crop),text)
    if len(matches)==1:return True
    raise ValueError('forward_query_not_rendered_yet')
   try:self.wait(visible,seconds=2);return
   except ValueError:
    if attempt:raise
  raise ValueError('forward_query_mismatch')
 def open_source(self):
  try:
   self.header_verified(SOURCE);self.r.check();self.r.proxy.call('scroll',{'x':1000,'y':500,'notches':40});time.sleep(.15);return
  except ValueError:pass
  s=self.layout['search'];x,y,w,h=s['box'];self.click(x+w/2,y+h/2);time.sleep(.08)
  if not focused(self.r.im(region(s['box']))):raise ValueError('forward_source_search_not_focused')
  self.type_query(SOURCE,s['box'])
  def result(im):
   if not popup_check(self.r,self.layout,self.profile):raise ValueError('forward_wait_source_results')
   rows=self.read(im,s['panel']);heads=text_rows(rows,'功能')
   if len(heads)!=1:raise ValueError('forward_source_function_section_missing')
   top=heads[0]['bounds'][1]+heads[0]['bounds'][3]
   bounds=[r['bounds'][1] for r in rows if r['bounds'][1]>top and norm(r['text']) in {'聊天记录','群聊','搜索网络结果'} and r['confidence']>=.9]
   if not bounds:raise ValueError('forward_source_result_boundary_missing')
   matches=[r for r in text_rows(rows,SOURCE) if top<r['bounds'][1]<min(bounds)]
   if len(matches)!=1:raise ValueError('forward_source_not_unique')
   time.sleep(.08);fresh=self.capture()
   if self.crop(im,s['panel']).tobytes()!=self.crop(fresh,s['panel']).tobytes():raise ValueError('forward_source_results_changed')
   return fresh,matches[0]
  im,row=self.wait(result,seconds=6)
  x,y,w,h=row['bounds'];self.click(s['panel'][0]+x+w/2,s['panel'][1]+y+h/2)
  previous=False
  def title(im):
   self.r.check();self.header_verified(SOURCE,im);return im
  self.wait(title,seconds=8);self.wait(title,seconds=8)
  self.r.proxy.call('scroll',{'x':1000,'y':500,'notches':40});time.sleep(.15)
 def source(self):
  im=self.capture();self.header_verified(SOURCE,im)
  panel=self.crop(im,list(rect(self.layout['messages'])));items=outgoing_two(panel,self.ocr,strict=True,fast=True)
  self.source_panel=panel;return items
 def checks(self,im,items):
  x=self.f['checkbox_x'];my=rect(self.layout['messages'])[1];states=[]
  for item in items:
   cy=my+item['box'][1]+28
   crop=im.crop((x-18,cy-18,x+18,cy+18));states.append(focused(crop))
  return states
 def dialog(self,im):
  rows=self.read(im,self.f['heading'])
  if not (text_rows(rows,'发送给') or text_rows(rows,'分别发送给')):raise ValueError('forward_recipient_dialog_missing')
  return rows
 def recipients(self,im,expected):
  self.dialog(im);return selected_names(self.read(im,self.f['selected_names']),expected)
 def select_recipient(self,name,expected):
  im=self.capture();self.dialog(im);box=self.f['search_box'];x,y,w,h=box;self.click(x+w/2,y+h/2);time.sleep(.06)
  if not focused(self.crop(self.capture(),box)):raise ValueError('forward_recipient_search_not_focused')
  self.type_query(name,box)
  def find(im):
   self.dialog(im);rows=self.read(im,self.f['results']);head=unique(rows,'联系人');top=head['bounds'][1]+head['bounds'][3]
   boundaries=[r['bounds'][1] for r in rows if r['bounds'][1]>top and norm(r['text']) in {'群聊','更多','搜索网络结果'} and r['confidence']>=.9];end=min(boundaries,default=self.f['results'][3])
   candidates=[r for r in text_rows(rows,name) if top<r['bounds'][1]<end]
   if len(candidates)!=1:raise ValueError('forward_recipient_missing_or_ambiguous')
   time.sleep(.08);fresh=self.capture()
   if self.crop(im,self.f['results']).tobytes()!=self.crop(fresh,self.f['results']).tobytes():raise ValueError('forward_recipient_results_changed')
   return fresh,candidates[0]
  im,row=self.wait(find)
  self.click(self.f['recipient_checkbox_x'],self.f['results'][1]+row['bounds'][1]+row['bounds'][3]/2)
  self.wait(lambda im:self.recipients(im,expected))
 def validate_final(self,im,recipients):
  self.recipients(im,recipients);rows=self.read(im,self.f['message_count'])
  labels=[r for r in rows if '逐条转发' in r['text'] and re.search(r'共\s*2\s*条消息',r['text']) and r['confidence']>=.9]
  if len(labels)!=1:raise ValueError('forward_selected_message_count_mismatch')
  unique(self.read(im,self.f['submit']),'分别发送('+str(len(recipients))+')')
  note=self.read(im,self.f['note'])
  if [norm(r['text']) for r in note]!=['给朋友留言']:raise ValueError('forward_unexpected_extra_note')
  return im
 def cancel(self):
  im=self.capture();self.dialog(im);unique(self.read(im,self.f['cancel']),'取消');x,y,w,h=self.f['cancel'];self.click(x+w/2,y+h/2);time.sleep(.15)
  im=self.capture()
  try:self.r.check();return
  except RuntimeError:pass
  rows=self.read(im,self.f['multi_toolbar']);toolbar=norm(''.join(r['text'] for r in rows if r['confidence']>=.9))
  if not all(t in toolbar for t in ['逐条转发','合并转发','复制','收藏']):raise ValueError('forward_cannot_exit_selection_safely')
  self.click(*self.f['multi_close']);self.wait_normal()
 def verify(self,messages,recipients):
  self.wait_normal();checks=[]
  for name in recipients:
   open_contact(self.r,name);self.r.proxy.call('scroll',{'x':1000,'y':500,'notches':30});time.sleep(.08);im=self.capture()
   self.header_verified(name,im)
   found=outgoing_two(self.crop(im,list(rect(self.layout['messages']))),self.ocr,fast=True)
   if [norm(i['text']) for i in found]!=[norm(x) for x in messages]:raise ValueError('forward_destination_messages_mismatch: '+name)
   checks.append({'recipient':name,'verified':True})
  return checks
 def run(self,args):
  start=time.perf_counter();submitted=False;prepared=False;path=None;record={}
  try:
   recipients=args.get('recipients');op=args.get('operation_id','');dry=args.get('dry_run',True)
   if not isinstance(recipients,list) or not 2<=len(recipients)<=5 or any(not isinstance(n,str) or not n.strip() or len(n)>80 or any(ord(c)<32 for c in n) for n in recipients) or len(set(recipients))!=len(recipients):raise ValueError('requires 2-5 unique exact authorized recipients')
   if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',op) or type(dry)!=bool or type(args.get('verify_existing',False))!=bool:raise ValueError('invalid operation_id or dry_run')
   STATE.mkdir(parents=True,exist_ok=True);STATE.chmod(0o700);path=STATE/(hashlib.sha256(op.encode()).hexdigest()+'.json')
   if path.exists():
    old=json.loads(path.read_text())
    if old['recipients']!=recipients:raise ValueError('forward_operation_recipient_binding_mismatch')
    if old['status'] in {'sending','ui_confirmed','send_uncertain'}:return {'content':[{'type':'text','text':json.dumps({'duplicate_request':True,**old},ensure_ascii=False)}],'isError':old['status']!='ui_confirmed'}
   self.layout=self.r.check();self.profile=json.loads(PROFILE.read_text());self.f=self.layout.get('forward')
   if not self.f:raise ValueError('needs_forward_calibration')
   if self.ocr is None:self.ocr=LocalOCR()
   stage=time.perf_counter();self.open_source();items=self.source();messages=[i['text'] for i in items];self.stages={'source_ms':round((time.perf_counter()-stage)*1000,2)}
   if path.exists() and json.loads(path.read_text()).get('source_messages',messages)!=messages:raise ValueError('forward_operation_source_binding_mismatch')
   prior=known_forward(messages,recipients)
   if prior and not dry:return {'content':[{'type':'text','text':json.dumps({'status':'already_forwarded_or_uncertain','source_messages':messages,'recipients':recipients,'previous_status':prior['status'],'instruction':'Do not forward the same content again; inspect existing record.'},ensure_ascii=False)}],'isError':prior['status']!='ui_confirmed'}
   stage=time.perf_counter();mx,my,_,_=rect(self.layout['messages']);box=items[0]['box']
   if self.r.im(self.layout['messages']).tobytes()!=self.source_panel.tobytes():raise ValueError('forward_source_changed_before_selection')
   self.r.proxy.call('click',{'x':round(mx+(box[0]+box[2])/2),'y':round(my+(box[1]+box[3])/2),'button':3});time.sleep(.08)
   self.click_label('多选');time.sleep(.08);im=self.capture();states=self.checks(im,items)
   if states[0] is not True:raise ValueError('forward_older_message_not_selected')
   if not states[1]:self.click(self.f['checkbox_x'],my+items[1]['box'][1]+28)
   im=self.wait(lambda im:im if self.checks(im,items)==[True,True] else (_ for _ in ()).throw(ValueError('forward_selection_not_ready')))
   self.click_label('逐条转发',self.f['forward_button']);self.wait(lambda im:self.dialog(im));prepared=True
   for index,name in enumerate(recipients):self.select_recipient(name,recipients[:index+1])
   im=self.wait(lambda im:self.validate_final(im,recipients));self.stages['prepare_recipients_ms']=round((time.perf_counter()-stage)*1000,2)
   stage=time.perf_counter();self.click(*self.f['preview_open']);time.sleep(.08)
   self.wait(lambda im:preview_matches(self.read(im,self.f['preview']),messages));self.click(*self.f['preview_close']);time.sleep(.08)
   im=self.wait(lambda im:self.validate_final(im,recipients));self.stages['preview_check_ms']=round((time.perf_counter()-stage)*1000,2)
   record={'status':'prepared','operation_id':op,'source_messages':messages,'recipients':recipients,'fingerprint':fingerprint(messages,recipients),'dry_run':dry}
   def save(status,**fields):
    record.update(status=status,**fields);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(record,ensure_ascii=False));tmp.chmod(0o600);os.replace(tmp,path)
   if dry:
    self.cancel()
    checks=[]
    if args.get('verify_existing',False) and prior and prior['status']=='ui_confirmed':
     verify_start=time.perf_counter();checks=self.verify(messages,recipients);self.stages['verify_existing_ms']=round((time.perf_counter()-verify_start)*1000,2)
    save('dry_run_confirmed',checks=checks,stages=self.stages,elapsed_ms=round((time.perf_counter()-start)*1000,2));return {'content':[{'type':'text','text':json.dumps({**record,'messages_sent':0,'cancelled':True},ensure_ascii=False)}]}
   fresh=self.capture()
   if self.crop(im,self.f['dialog_right']).tobytes()!=self.crop(fresh,self.f['dialog_right']).tobytes():raise ValueError('forward_final_dialog_changed')
   save('sending',submitted_at_unix=time.time());submitted=True;x,y,w,h=self.f['submit'];self.click(x+w/2,y+h/2)
   stage=time.perf_counter();checks=self.verify(messages,recipients);self.stages['commit_verify_ms']=round((time.perf_counter()-stage)*1000,2)
   save('ui_confirmed',checks=checks,stages=self.stages,elapsed_ms=round((time.perf_counter()-start)*1000,2));return {'content':[{'type':'text','text':json.dumps(record,ensure_ascii=False)}]}
  except Exception as error:
   if submitted and path:
    record['status']='send_uncertain';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(record,ensure_ascii=False));tmp.chmod(0o600);os.replace(tmp,path)
   result=self.r.fallback(error);result['content'].insert(0,{'type':'text','text':json.dumps({'status':'send_uncertain' if submitted else 'forward_stopped','submitted':submitted,'stages':self.stages,'elapsed_ms':round((time.perf_counter()-start)*1000,2),'instruction':'Never retry a submitted forward. Inspect screenshot; dry-run preparation may remain open.'},ensure_ascii=False)});return result
