"""One local workflow for fresh visible-contact selection and verified sends."""
import csv,hashlib,io,json,re,subprocess,time,unicodedata
import auto_file_helper as auto

def exact(value):return unicodedata.normalize('NFC',value)
def lines(im):
 b=io.BytesIO();im.save(b,format='PNG')
 r=subprocess.run(['tesseract','stdin','stdout','--tessdata-dir',str(auto.BASE/'tessdata'),'-l','chi_sim+eng','--psm','6','-c','tessedit_create_tsv=1'],input=b.getvalue(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,check=True)
 groups={}
 for row in csv.DictReader(io.StringIO(r.stdout.decode()),delimiter='\t',quoting=csv.QUOTE_NONE):
  if not row.get('text','').strip() or float(row['conf'])<0:continue
  key=tuple(row[k] for k in ('page_num','block_num','par_num','line_num'));groups.setdefault(key,[]).append(row)
 result=[]
 for words in groups.values():
  # A conversation row has a right-aligned clock; previews lack this marker.
  clocks=[w for w in words if re.fullmatch(r'\d{1,2}:\d{2}',w['text']) and int(w['left'])>im.width-85]
  if len(clocks)!=1:continue
  words=[w for w in words if w is not clocks[0]]
  if not words:continue
  result.append({'text':' '.join(w['text'] for w in words),'confidence':min(float(w['conf']) for w in words),'x':min(int(w['left']) for w in words),'y':min(int(w['top']) for w in words),'width':max(int(w['left'])+int(w['width']) for w in words)-min(int(w['left']) for w in words),'height':max(int(w['top'])+int(w['height']) for w in words)-min(int(w['top']) for w in words)})
 return result

def unique(rows,recipient):
 matches=[r for r in rows if exact(r['text'])==exact(recipient)]
 if len(matches)!=1:raise ValueError('contact_not_unique_or_not_visible: inspect fresh screenshot; never guess a row')
 if matches[0]['confidence']<85:raise ValueError('contact_low_confidence')
 return matches[0]

def validate(items):
 if not isinstance(items,list) or not 1<=len(items)<=10:raise ValueError('messages must contain 1-10 explicit authorized sends')
 ids=set()
 for item in items:
  if not isinstance(item,dict):raise ValueError('invalid message')
  for key in ('recipient','text'):
   v=item.get(key)
   if not isinstance(v,str) or not v.strip() or len(v)>80 or any(ord(c)<32 for c in v):raise ValueError('invalid '+key)
  op=item.get('operation_id','')
  if not isinstance(op,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',op) or op in ids:raise ValueError('invalid or repeated operation_id')
  ids.add(op)

def select(regions,recipient):
 start=time.perf_counter();layout=regions.check()
 # Fresh calibrated sidebar; no remembered row coordinates. Name column only.
 hx=int(layout['header'].split(',')[0]);W,H=layout['size']
 x=max(110,int(hx*.36));y=145;w=hx-x-25;h=H-y-100
 if w<100 or h<100:raise ValueError('contact_region_invalid')
 region=f'{x},{y} {w}x{h}'
 im=regions.im(region);row=unique(lines(im),recipient)
 # Recheck the entire contact column immediately before clicking it.
 regions.check()
 if regions.im(region).tobytes()!=im.tobytes():raise ValueError('contact_list_changed: inspect before selecting')
 regions.proxy.call('click',{'x':x+row['x']+max(1,row['width']//2),'y':y+row['y']+max(1,row['height']//2)})
 selected=time.perf_counter();deadline=selected+3;stable=0
 while time.perf_counter()<deadline:
  time.sleep(.08);regions.check();title,confidence=regions.header()
  if exact(title)==exact(recipient) and confidence>=85:stable+=1
  else:stable=0
  if stable>=2:return {'select_ms':round((selected-start)*1000,2),'wait_title_ms':round((time.perf_counter()-selected)*1000,2),'title_confidence':confidence}
 raise ValueError('recipient_switch_timeout: nothing sent')

def select_element(regions,recipient):
 # Explicit experiment: consume the structured element map, never static row coordinates.
 from wechat_elements import ElementMap
 start=time.perf_counter()
 if not hasattr(regions,'element_map'):regions.element_map=ElementMap(regions)
 mapping=regions.element_map.inspect();mapped=time.perf_counter()
 matches=[e for e in mapping['elements'] if e['role']=='recent_chat_name' and exact(e['text'])==exact(recipient) and e['source']=='ocr' and e['confidence']>=85]
 if len(matches)>1:raise ValueError('element_recipient_missing_or_ambiguous')
 if not matches:
  # The map established the target is not visible; use the guarded local search path.
  if not any(e['role']=='search_field' and e['source']=='reviewed_layout' for e in mapping['elements']):raise ValueError('element_recipient_missing_or_ambiguous')
  from wechat_search import select as search_select
  search_stages=search_select(regions,recipient)
  return {'element_map_ms':round((mapped-start)*1000,2),'frame_id':mapping['frame_id'],**search_stages,'selected_via':'text_element_map_then_local_search'}
 if time.time()-mapping['captured_at_unix']>2:raise ValueError('element_frame_expired')
 regions.check();contact_region,digest=regions.element_map.last_contacts
 if hashlib.sha256(regions.im(contact_region).tobytes()).hexdigest()!=digest:raise ValueError('element_contacts_changed')
 row=matches[0]
 current=next((e for e in mapping['elements'] if e['role']=='chat_title'),None)
 already_open=bool(current and exact(current['text'])==exact(recipient) and current['confidence']>=85)
 if not already_open:regions.proxy.call('click',{'x':row['center'][0],'y':row['center'][1]})
 clicked=time.perf_counter();deadline=clicked+3;stable=0
 while time.perf_counter()<deadline:
  time.sleep(.08)
  try:regions.check();title,confidence=regions.header()
  except RuntimeError:
   stable=0;continue
  if exact(title)==exact(recipient) and confidence>=85:stable+=1
  else:stable=0
  if stable>=2:return {'element_map_ms':round((mapped-start)*1000,2),'revalidate_click_ms':round((clicked-mapped)*1000,2),'wait_title_ms':round((time.perf_counter()-clicked)*1000,2),'title_confidence':confidence,'frame_id':mapping['frame_id'],'element_id':row['id'],'selected_via':'text_element_map'}
 raise ValueError('element_recipient_switch_timeout: nothing sent')

def run(regions,args):
 start=time.perf_counter();completed=[];current=None;stages={};one=start
 try:
  items=args.get('messages');validate(items)
  for item in items:
   one=time.perf_counter();recipient=item['recipient'];current=recipient;stages={}
   path=auto.STATE/(hashlib.sha256(item['operation_id'].encode()).hexdigest()+'.json')
   if path.exists():
    # Existing sender validates recipient/text binding and returns without replay.
    result=auto.send(regions.proxy,item,regions=regions,recipient=recipient);stages={'duplicate_request':True}
   else:
    if args.get('_elements'):stages=select_element(regions,recipient)
    elif args.get('_search'):
     from wechat_search import select as search_select
     stages=search_select(regions,recipient)
    else:stages=select(regions,recipient)
    sent=time.perf_counter()
    result=auto.send(regions.proxy,item,regions=regions,recipient=recipient)
    stages['send_verify_ms']=round((time.perf_counter()-sent)*1000,2)
   record=json.loads(next(c['text'] for c in result['content'] if c['type']=='text'))
   completed.append({'recipient':recipient,'result':record,'stages':stages,'total_ms':round((time.perf_counter()-one)*1000,2)})
   if result.get('isError') or record.get('status')!='ui_confirmed':raise ValueError('previous_send_uncertain: batch stopped')
  return {'content':[{'type':'text','text':json.dumps({'status':'ui_confirmed','completed':completed,'elapsed_ms':round((time.perf_counter()-start)*1000,2)},ensure_ascii=False)}]}
 except Exception as error:
  result=regions.fallback(error)
  result['content'].insert(0,{'type':'text','text':json.dumps({'status':'workflow_stopped','completed':completed,'stopped_recipient':current,'stopped_stages':stages,'stopped_elapsed_ms':round((time.perf_counter()-one)*1000,2),'elapsed_ms':round((time.perf_counter()-start)*1000,2),'instruction':'No automatic retries. Inspect error and screenshot; completed messages must not be resent.'},ensure_ascii=False)})
  return result
