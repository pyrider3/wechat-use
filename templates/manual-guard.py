#!/usr/bin/python3
"""MCP proxy: allow concurrent viewing, reduce deterministic UI round trips."""
import base64,fcntl,hashlib,json,os,pathlib,queue,re,secrets,subprocess,sys,threading,time
BASE=pathlib.Path(__file__).resolve().parent
RUNTIME=pathlib.Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))
ELEMENTS_DISABLED=pathlib.Path.home()/'.config/wbox-mcp/wechat/elements.disabled'
OBSERVE={'screenshot','list_windows','get_size','get_mouse_position','tail_log'}
EXTRA=[
 {'name':'paste_and_capture','description':'Paste Chinese text in an already visually verified WeChat chat, then return a screenshot and one-use preparation token. Does NOT send. Supply input coordinates and a header-only guard_region from a fresh screenshot. Verify recipient and complete draft in the returned image before send_prepared.','inputSchema':{'type':'object','properties':{'text':{'type':'string','minLength':1,'maxLength':16000},'x':{'type':'integer','minimum':0},'y':{'type':'integer','minimum':0},'guard_region':{'type':'string','pattern':r'^\d+,\d+ \d+x\d+$'}},'required':['text','x','y','guard_region'],'additionalProperties':False}},
 {'name':'send_prepared','description':'Send ONCE after visually verifying recipient and draft from paste_and_capture. Requires its one-use token; refuses if active window or captured header changed, token expired. Returns a post-send screenshot, NOT an automatic delivery guarantee. Never retry an uncertain send.','inputSchema':{'type':'object','properties':{'token':{'type':'string','minLength':1}},'required':['token'],'additionalProperties':False}}]
EXTRA.append({'name':'send_to_file_helper','description':'Experimental one-call send ONLY to the currently open File Transfer Assistant chat. Requires explicit user authorization, calibrated layout, exact high-confidence OCR recipient, empty draft and a unique operation_id. Verifies draft by clipboard, sends once, verifies green bubble and empty input. Wrong chat/layout refuses. SEND_UNCERTAIN or duplicate_request must not be retried with a new id without inspection.','inputSchema':{'type':'object','properties':{'text':{'type':'string','minLength':1,'maxLength':80},'operation_id':{'type':'string','pattern':'^[A-Za-z0-9_-]{8,80}$'}},'required':['text','operation_id'],'additionalProperties':False}})
for name,description,schema in [
 ('calibrate_regions','Capture one full frame and build region anchors. Only calibrate a normal unobscured WeChat window after inspecting layout. Optional layout supplies new rectangles from a fresh screenshot.',{'type':'object','properties':{'layout':{'type':'object'}},'additionalProperties':False}),
 ('inspect_regions','Read current WeChat title, draft OCR and latest outgoing message from small regions. Normal result is text only, cached only for identical images. Layout changes/popups return a full screenshot and refuse actions. Contacts OCR optional.',{'type':'object','properties':{'contacts':{'type':'boolean'}},'additionalProperties':False}),
 ('send_partitioned_to_file_helper','Send short authorized text only to the already-open File Transfer Assistant. Uses calibrated regions and OCR, no full frame on normal success. Layout/popups/uncertain send return fresh full screenshot. Unique operation_id prevents resend.',{'type':'object','properties':{'text':{'type':'string','maxLength':80,'minLength':1},'operation_id':{'type':'string','pattern':'^[A-Za-z0-9_-]{8,80}$'}},'required':['text','operation_id'],'additionalProperties':False})]:EXTRA.append({'name':name,'description':description,'inputSchema':schema})
for contact_tool in ('send_to_contact','send_partitioned_to_contact'):
 EXTRA.append({'name':contact_tool,'description':'Send authorized short text to an already-open, visually selected ordinary contact. Exact case-sensitive recipient title OCR required before pasting and sending. Supply the unique user-authorized remark/name; does not search or navigate. Ambiguous names require visual contact identity review. Same operation_id is bound to recipient and text. Never retry SEND_UNCERTAIN.', 'inputSchema':{'type':'object','properties':{'recipient':{'type':'string','minLength':1,'maxLength':80},'text':{'type':'string','minLength':1,'maxLength':80},'operation_id':{'type':'string','pattern':'^[A-Za-z0-9_-]{8,80}$'}},'required':['recipient','text','operation_id'],'additionalProperties':False}})
EXTRA.append({'name':'send_contacts_workflow','description':'Select each uniquely named visible recent contact from fresh OCR, wait for exact high-confidence title twice, then send authorized short text once with draft/recipient/result checks. Holds action lock across the entire batch. Stops on missing/ambiguous contact, changed layout/list, or uncertain send; returns fresh screenshot. No automatic search or scrolling. Each operation_id is bound to recipient and text.','inputSchema':{'type':'object','properties':{'messages':{'type':'array','minItems':1,'maxItems':10,'items':{'type':'object','properties':{'recipient':{'type':'string','minLength':1,'maxLength':80},'text':{'type':'string','minLength':1,'maxLength':80},'operation_id':{'type':'string','pattern':'^[A-Za-z0-9_-]{8,80}$'}},'required':['recipient','text','operation_id'],'additionalProperties':False}}},'required':['messages'],'additionalProperties':False}})
search_schema=next(t['inputSchema'] for t in EXTRA if t['name']=='send_contacts_workflow')
EXTRA.append({'name':'send_elements_workflow','description':'Explicit experimental send batch using text element map names and centers for selection; revalidates fresh contact pixels, verifies exact recipient twice and uses existing draft/idempotency/result checks. Disabled by elements.disabled. Does not replace stable workflow. Requires explicit user authorization.','inputSchema':search_schema})
EXTRA.append({'name':'search_contacts_workflow','description':'Search exact user-authorized remarks in calibrated local Contacts section, reject groups/network results/ambiguity, wait for exact chat title twice, then send with existing draft/recipient/idempotency checks. Stops on uncertainty. Requires search layout calibration.','inputSchema':search_schema})
EXTRA.append({'name':'search_open_contact','description':'Search and open an exact unique local contact, verify title, without composing or sending. Missing/ambiguous/unknown layouts return fresh screenshot. Requires search calibration.','inputSchema':{'type':'object','properties':{'recipient':{'type':'string','minLength':1,'maxLength':80}},'required':['recipient'],'additionalProperties':False}})
EXTRA.append({'name':'inspect_ui_elements','description':'Optional experimental read-only text element map with OCR names, confidence, bounds, centers and frame ID. Main chat only; normal output contains no image. Layout/unknown popup/low-confidence title returns screenshot for visual review. Does not click or send; existing guarded workflows remain preferred.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}})
EXTRA.append({'name':'group_member_counts','description':'Read-only local batch: search group-name keyword, enumerate complete local Groups section, reopen each fresh result and verify exact group title/member count twice. No messages or group edits. Returns text table data; uncertain/truncated/duplicate results return partial data and fresh screenshot. Requires optional local group OCR runtime and group_header calibration.','inputSchema':{'type':'object','properties':{'query':{'type':'string','minLength':1,'maxLength':80},'max_groups':{'type':'integer','minimum':1,'maximum':10}},'required':['query'],'additionalProperties':False}})
EXTRA.append({'name':'forward_latest_two','description':'Guarded local forwarding of File Transfer Assistant latest TWO short outgoing plain-text bubbles to 2-5 authorized unique contacts. Default dry_run prepares, verifies full message preview and exact recipients, then cancels without sending. Send mode rejects previously forwarded identical content/recipients and submits once with durable anti-resend journal; verifies each destination. Unsupported media/layout/ambiguity stops with screenshot. Requires reviewed forward calibration and optional local OCR.','inputSchema':{'type':'object','properties':{'recipients':{'type':'array','minItems':2,'maxItems':5,'uniqueItems':True,'items':{'type':'string','minLength':1,'maxLength':80}},'operation_id':{'type':'string','pattern':'^[A-Za-z0-9_-]{8,80}$'},'dry_run':{'type':'boolean','default':True},'verify_existing':{'type':'boolean','default':False}},'required':['recipients','operation_id'],'additionalProperties':False}})
OBSERVE.add('inspect_regions')
class Proxy:
 def __init__(self,command):
  self.p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
  self.counter=0;self.pending={};self.lock=threading.Lock();self.output=threading.Lock();self.tokens={}
  threading.Thread(target=self.reader,daemon=True).start()
 def emit(self,r):
  with self.output:print(json.dumps(r,ensure_ascii=False),flush=True)
 def reader(self):
  for line in self.p.stdout:
   try:r=json.loads(line)
   except ValueError:continue
   q=self.pending.get(r.get('id'))
   if q:q.put(r)
   else:self.emit(r)
 def rpc(self,method,params):
  self.counter+=1;rid='proxy-'+str(self.counter);q=queue.Queue();self.pending[rid]=q
  self.p.stdin.write(json.dumps({'jsonrpc':'2.0','id':rid,'method':method,'params':params})+'\n');self.p.stdin.flush()
  try:
   r=q.get(timeout=20)
   if 'error' in r:raise RuntimeError(str(r['error']))
   return r.get('result',{})
  finally:self.pending.pop(rid,None)
 def call(self,name,args):
  r=self.rpc('tools/call',{'name':name,'arguments':args})
  if r.get('isError'):raise RuntimeError('upstream_error: '+str(r.get('content')))
  for c in r.get('content',[]):
   if c.get('type')=='text':
    if c.get('text','').startswith(('Error:','grim failed:','Unknown tool:')):raise RuntimeError(c['text'])
    try:payload=json.loads(c['text'])
    except ValueError:continue
    if isinstance(payload,dict) and payload.get('error'):raise RuntimeError(str(payload['error']))
  return r
 def focus(self):
  r=self.call('list_windows',{})
  windows=json.loads(next(c['text'] for c in r['content'] if c['type']=='text'))['windows']
  active=[w for w in windows if w.get('activated')]
  if len(active)!=1 or active[0].get('app_id')!='wechat':raise RuntimeError('focus_mismatch: activate and inspect WeChat first')
  return active[0]['app_id'],active[0]['title']
 def header(self,region):
  r=self.call('screenshot',{'region':region})
  data=next(c['data'] for c in r['content'] if c['type']=='image')
  return hashlib.sha256(base64.b64decode(data)).hexdigest()
 def fast(self,name,args):
  if name in {'inspect_ui_elements','send_elements_workflow'} and ELEMENTS_DISABLED.exists():return {"isError":True,"content":[{"type":"text","text":"element_map_disabled: use inspect_regions or existing workflows"}]}
  if name in {'calibrate_regions','inspect_regions','send_partitioned_to_file_helper','send_partitioned_to_contact','send_contacts_workflow','search_contacts_workflow','search_open_contact','inspect_ui_elements','send_elements_workflow','group_member_counts','forward_latest_two'}:
   from wechat_regions import Regions
   if not hasattr(self,'regions'):self.regions=Regions(self)
   if name=="forward_latest_two":
    from wechat_forward import Forwarder
    if not hasattr(self.regions,'forwarder'):self.regions.forwarder=Forwarder(self.regions)
    return self.regions.forwarder.run(args)
   if name=="group_member_counts":
    from wechat_groups import GroupReader
    if not hasattr(self.regions,'group_reader'):self.regions.group_reader=GroupReader(self.regions)
    return self.regions.group_reader.run(args)
   if name=="inspect_ui_elements":
    from wechat_elements import ElementMap
    if not hasattr(self.regions,'element_map'):self.regions.element_map=ElementMap(self.regions)
    return self.regions.element_map.run()
   if name=="search_open_contact":
    from wechat_search import select
    try:return {'content':[{'type':'text','text':json.dumps(select(self.regions,args.get('recipient')),ensure_ascii=False)}]}
    except Exception as e:return self.regions.fallback(e)
   if name in {"send_contacts_workflow","search_contacts_workflow","send_elements_workflow"}:
    from wechat_workflow import run
    return run(self.regions,{**args,"_search":name=="search_contacts_workflow","_elements":name=="send_elements_workflow"})
   return self.regions.run(name,args)
  if name in {'send_to_file_helper','send_to_contact'}:
   from auto_file_helper import send
   return send(self,args,recipient=args.get("recipient","") if name=="send_to_contact" else "文件传输助手")
  if name=='paste_and_capture':
   if not isinstance(args.get('text'),str) or not 0<len(args['text'])<=16000:raise ValueError('invalid text')
   region=args.get('guard_region','')
   if not re.fullmatch(r'\d+,\d+ \d+x\d+',region):raise ValueError('invalid guard_region')
   if any(not isinstance(args.get(k),int) or args[k]<0 for k in ('x','y')):raise ValueError('invalid input coordinates')
   focus=self.focus();header=self.header(region)
   self.call('click',{'x':args['x'],'y':args['y']})
   self.call('clipboard_write',{'text':args['text']})
   self.call('key',{'shortcut':'ctrl+v'})
   time.sleep(.15)
   if self.focus()!=focus or self.header(region)!=header:raise RuntimeError('context_changed: draft may have been pasted; inspect before further action')
   token=secrets.token_urlsafe(18)
   self.tokens={k:v for k,v in self.tokens.items() if time.monotonic()-v['time']<90}
   self.tokens[token]={'focus':focus,'header':header,'region':region,'time':time.monotonic(),'text':args['text']}
   r=self.call('screenshot',{})
   r['content'].insert(0,{'type':'text','text':json.dumps({'prepared':True,'token':token,'expires_in_seconds':90,'submitted':False,'instruction':'Verify chat recipient and entire draft in this screenshot before sending.'})})
   return r
  token=args.get('token');prepared=self.tokens.pop(token,None) # Consume BEFORE sending, including uncertain/error cases.
  if not prepared or time.monotonic()-prepared['time']>90:raise ValueError('invalid_or_expired_token: inspect and prepare again; do not resend blindly')
  if self.focus()!=prepared['focus'] or self.header(prepared['region'])!=prepared['header']:raise RuntimeError('context_changed: nothing sent')
  # Read the current input back without trusting a stale clipboard value.
  self.call('clipboard_write',{'text':'draft-check-'+secrets.token_hex(12)})
  self.call('key',{'shortcut':'ctrl+a'})
  self.call('key',{'shortcut':'ctrl+c'})
  time.sleep(.03)
  copied=self.call('clipboard_read',{})
  actual=None
  for content in copied.get('content',[]):
   if content.get('type')=='text':
    actual=content['text']
  self.call('key',{'shortcut':'ctrl+End'})
  self.call('clipboard_write',{'text':prepared['text']})
  if actual!=prepared['text']:raise RuntimeError('draft_changed_or_unreadable: nothing sent; inspect draft')
  if self.focus()!=prepared['focus'] or self.header(prepared['region'])!=prepared['header']:raise RuntimeError('context_changed: nothing sent')
  self.call('key',{'shortcut':'Return'})
  time.sleep(.25)
  try:r=self.call('screenshot',{})
  except Exception as e:raise RuntimeError('SEND_UNCERTAIN: Enter already dispatched, do not retry; '+str(e))
  r['content'].insert(0,{'type':'text','text':'Enter dispatched once. Inspect the message bubble, input field and any failure indicator; this is not an automatic delivery confirmation.'})
  return r
 def handle(self,req):
  method=req.get('method');params=req.get('params',{});name=params.get('name')
  if 'id' not in req:
   self.p.stdin.write(json.dumps(req)+'\n');self.p.stdin.flush();return
  started=time.perf_counter()
  try:
   if method=='tools/call' and name not in OBSERVE:
    with (RUNTIME/'wbox-wechat-action.lock').open('a') as action:
     try:fcntl.flock(action,fcntl.LOCK_EX|fcntl.LOCK_NB)
     except BlockingIOError:raise RuntimeError('automation_busy: another agent is executing an action')
     result=self.fast(name,params.get('arguments',{})) if name in {'paste_and_capture','send_prepared','send_to_file_helper','send_to_contact','calibrate_regions','send_partitioned_to_file_helper','send_partitioned_to_contact','send_contacts_workflow','search_contacts_workflow','search_open_contact','inspect_ui_elements','send_elements_workflow','group_member_counts','forward_latest_two'} else self.rpc(method,params)
   else:
    result=self.fast(name,params.get('arguments',{})) if method=='tools/call' and name=='inspect_regions' else self.rpc(method,params)
    if method=='tools/list':result['tools'].extend(t for t in EXTRA if t['name'] not in {'inspect_ui_elements','send_elements_workflow'} or not ELEMENTS_DISABLED.exists())
   response={'jsonrpc':'2.0','id':req['id'],'result':result}
  except Exception as e:response={'jsonrpc':'2.0','id':req['id'],'result':{'isError':True,'content':[{'type':'text','text':str(e)}]}}
  if method=='tools/call':
   path=pathlib.Path.home()/'.local/state/wbox-wechat/timings.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
   with path.open('a') as f:f.write(json.dumps({'tool':name,'elapsed_ms':round((time.perf_counter()-started)*1000,2),'error':bool(response['result'].get('isError'))})+'\n')
   path.chmod(0o600)
  self.emit(response)
 def close(self):
  self.p.stdin.close()
  try:self.p.wait(timeout=3)
  except subprocess.TimeoutExpired:self.p.terminate();self.p.wait(timeout=3)
if __name__=='__main__':
 proxy=Proxy([str(BASE/'wbox-mcp-direct'),*sys.argv[1:]])
 try:
  for line in sys.stdin:proxy.handle(json.loads(line))
 finally:proxy.close()
