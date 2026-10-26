"""Read-only batch group lookup: search -> fresh result -> group title/member count."""
import atexit,base64,hashlib,io,json,os,pathlib,queue,re,subprocess,threading,time
import auto_file_helper as auto
from wechat_regions import PROFILE
from wechat_search import region,focused,popup_check

def group_rows(rows,query):
 headings=[r for r in rows if auto.norm(r['text'])=='群聊' and r['confidence']>=.9]
 if len(headings)!=1:raise ValueError('group_section_missing_or_unreadable')
 start=headings[0]['bounds'][1]+headings[0]['bounds'][3]
 ends=[r['bounds'][1] for r in rows if r['bounds'][1]>start and auto.norm(r['text']) in {'搜索网络结果','更多','聊天记录','联系人','公众号'} and r['confidence']>=.9]
 if not ends:raise ValueError('group_results_incomplete: no verified section boundary')
 end=min(ends);section=[r for r in rows if start<r['bounds'][1]<end]
 if any('查看更多' in auto.norm(r['text']) for r in section):raise ValueError('group_results_incomplete: more results require review')
 matches=[r for r in section if auto.norm(query) in auto.norm(r['text']) and not auto.norm(r['text']).startswith('包含:')]
 if not matches:raise ValueError('no_matching_groups')
 if any(r['confidence']<.9 or '...' in r['text'] or '…' in r['text'] for r in matches):raise ValueError('group_name_unreliable_or_truncated')
 if len({auto.norm(r['text']) for r in matches})!=len(matches):raise ValueError('duplicate_group_names: identity review required')
 return sorted(matches,key=lambda r:r['bounds'][1])

def parse_title(rows,expected):
 if len(rows)!=1 or rows[0]['confidence']<.9:raise ValueError('group_title_unreliable')
 text=auto.norm(rows[0]['text']);m=re.fullmatch(r'(.+)\((\d{1,6})\)',text)
 if not m or m[1]!=auto.norm(expected):raise ValueError('group_title_mismatch: expected='+repr(auto.norm(expected))+' observed='+repr(text))
 count=int(m[2])
 if count<1:raise ValueError('group_count_invalid')
 return count,rows[0]['confidence']

class LocalOCR:
 def __init__(self):
  python=auto.BASE/'group-ocr-venv/bin/python'
  if not python.exists():raise ValueError('group_ocr_dependency_missing: install optional isolated group OCR runtime')
  env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
  self.log=open(os.devnull,'w');self.p=subprocess.Popen([str(python),str(auto.BASE/'group_ocr_worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True,bufsize=1,env=env)
  self.responses=queue.Queue();self.cache={};self.counter=0
  def read():
   for line in self.p.stdout:
    try:self.responses.put(json.loads(line))
    except ValueError:pass
   self.responses.put({'error':'OCR worker exited'})
  threading.Thread(target=read,daemon=True).start();atexit.register(self.close)
 def close(self):
  if self.p.poll() is None:
   self.p.terminate()
   try:self.p.wait(timeout=2)
   except subprocess.TimeoutExpired:self.p.kill();self.p.wait()
  self.log.close()
 def read(self,im):
  key=(im.size,hashlib.sha256(im.tobytes()).hexdigest())
  if key in self.cache:return self.cache[key]
  self.counter+=1;request_id=self.counter
  b=io.BytesIO();im.save(b,format='PNG');self.p.stdin.write(json.dumps({'id':request_id,'png':base64.b64encode(b.getvalue()).decode()})+'\n');self.p.stdin.flush()
  deadline=time.perf_counter()+20
  while True:
   try:r=self.responses.get(timeout=max(.01,deadline-time.perf_counter()))
   except queue.Empty:
    self.close();raise ValueError('group_ocr_timeout')
   if r.get('id')==request_id:break
   if r.get('error') and r.get('id') is None:raise ValueError(r['error'])
   if time.perf_counter()>=deadline:
    self.close();raise ValueError('group_ocr_timeout')
  if r.get('error'):raise ValueError(r['error'])
  if len(self.cache)>80:self.cache={}
  self.cache[key]=r['rows'];return r['rows']

class GroupReader:
 def __init__(self,regions):self.r=regions;self.ocr=None
 def search(self,query,layout,profile):
  r=self.r;s=layout['search'];r.check()
  x,y,w,h=s['box'];r.proxy.call('click',{'x':x+w//2,'y':y+h//2});time.sleep(.08)
  if not focused(r.im(region(s['box']))):raise ValueError('group_search_not_focused')
  r.proxy.call('key',{'shortcut':'ctrl+a'});r.proxy.call('clipboard_write',{'text':query});r.proxy.call('key',{'shortcut':'ctrl+v'});time.sleep(.08)
  if not focused(r.im(region(s['box']))) or auto.copy_draft(r.proxy)!=query:raise ValueError('group_query_mismatch')
  deadline=time.perf_counter()+6;last=None
  while time.perf_counter()<deadline:
   try:
    if not popup_check(r,layout,profile):raise ValueError('group_waiting_search')
    frame=r.im(region(s['panel']));rows=group_rows(self.ocr.read(frame),query)
    if r.im(region(s['panel'])).tobytes()!=frame.tobytes():raise ValueError('group_search_changing')
    popup_check(r,layout,profile);return rows,frame
   except ValueError as e:
    last=e
    if any(k in str(e) for k in ('duplicate','unexpected','changed','timeout')):raise
    time.sleep(.1)
  raise ValueError(str(last or 'group_search_timeout'))
 def count(self,name,header):
  deadline=time.perf_counter()+5;previous=None;stable=0;last=None
  while time.perf_counter()<deadline:
   time.sleep(.08)
   try:
    self.r.check();count,confidence=parse_title(self.ocr.read(self.r.im(header)),name)
    stable=stable+1 if previous==count else 1;previous=count
    if stable>=2:return count,confidence
   except (ValueError,RuntimeError) as e:last=e;stable=0
  raise ValueError('group_title_count_unverified: '+str(last))
 def run(self,args):
  start=time.perf_counter();completed=[]
  try:
   query=args.get('query');limit=args.get('max_groups',10)
   if not isinstance(query,str) or not query.strip() or len(query)>80 or any(ord(c)<32 for c in query):raise ValueError('invalid group query')
   if type(limit)!=int or not 1<=limit<=10:raise ValueError('max_groups must be 1-10')
   layout=self.r.check();profile=json.loads(PROFILE.read_text())
   if 'search' not in layout or 'group_header' not in layout:raise ValueError('needs_group_search_calibration')
   if self.ocr is None:self.ocr=LocalOCR()
   rows,frame=self.search(query,layout,profile);names=[r['text'] for r in rows]
   if len(names)>limit:raise ValueError('matching_groups_exceed_limit')
   for index,name in enumerate(names):
    one=time.perf_counter()
    if index:
     rows,frame=self.search(query,layout,profile)
     if {auto.norm(r['text']) for r in rows}!={auto.norm(n) for n in names}:raise ValueError('group_results_changed: partial results only')
    row=next(r for r in rows if auto.norm(r['text'])==auto.norm(name));s=layout['search']
    popup_check(self.r,layout,profile)
    if self.r.im(region(s['panel'])).tobytes()!=frame.tobytes():raise ValueError('group_search_changing_before_click')
    x,y,w,h=row['bounds'];self.r.proxy.call('click',{'x':round(s['panel'][0]+x+w/2),'y':round(s['panel'][1]+y+h/2)})
    count,confidence=self.count(name,layout['group_header'])
    completed.append({'group':name,'members':count,'title_confidence':confidence,'verified_frames':2,'elapsed_ms':round((time.perf_counter()-one)*1000,2)})
   return {'content':[{'type':'text','text':json.dumps({'status':'verified','query':query,'groups':completed,'complete':True,'elapsed_ms':round((time.perf_counter()-start)*1000,2),'messages_sent':0},ensure_ascii=False)}]}
  except Exception as error:
   result=self.r.fallback(error);result['content'].insert(0,{'type':'text','text':json.dumps({'status':'group_lookup_stopped','groups':completed,'complete':False,'elapsed_ms':round((time.perf_counter()-start)*1000,2),'messages_sent':0},ensure_ascii=False)});return result
