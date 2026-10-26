"""Calibrated local-contact search. Never selects group/network search entries."""
import json,time,unicodedata
import auto_file_helper as auto
from wechat_regions import inventory

def exact(s):return unicodedata.normalize('NFC',s)
def region(box):return f'{box[0]},{box[1]} {box[2]}x{box[3]}'
def focused(im):
 raw=im.convert('RGB').tobytes()
 return sum(1 for i in range(0,len(raw),3) if raw[i+1]>120 and raw[i]<90 and raw[i+2]<180 and raw[i+1]-raw[i]>50)>100

def popup_check(regions,layout,profile):
 regions.proxy.focus();inv=inventory()
 if inv['size']!=layout['size']:raise ValueError('search_layout_changed')
 main=[w for w in inv['windows'] if not w['override_redirect'] and all(w[k]==v for k,v in profile['geometry'].items())]
 if len(main)!=1:raise ValueError('search_main_window_changed')
 others=[w for w in inv['windows'] if w['id']!=main[0]['id']]
 if len(others)>1:raise ValueError('search_unexpected_popup')
 if others:
  w=others[0];g=layout['search']['popup']
  if w['override_redirect'] or any(w[k]!=g[k] for k in ('x','y','width')) or not 50<=w['height']<=g['max_height']:raise ValueError('search_unexpected_popup')
 return bool(others)

def read_contacts(regions,layout,frame=None):
 s=layout['search'];px,py,_,_=s['panel'];frame=frame if frame is not None else regions.im(region(s['panel']))
 def crop(box):
  x,y,w,h=box;return frame.crop((x-px,y-py,x-px+w,y-py+h))
 heading,conf=auto.ocr(crop(s['heading']),7)
 if auto.norm(heading)!='联系人' or conf<85:raise ValueError('search_no_local_contacts')
 rows=[]
 for index in range(s['max_rows']):
  top=s['row_top']+index*s['row_height']
  # A new section starts at a row boundary. Verify its actual label, not its position.
  label,lc=auto.ocr(crop([s['heading'][0],top+8,s['heading'][2],45]),7)
  if auto.norm(label) in {'群聊','更多','公众号','聊天记录','搜索网络结果'} and lc>=80:
   if not rows:raise ValueError('search_empty_contacts')
   return rows
  words,c=auto.ocr(crop([s['name_x'],top+s['name_offset'],s['name_width'],s['name_height']]),7)
  if not words or c<85:raise ValueError('search_contact_unreadable_or_more_results')
  rows.append({'text':words,'confidence':c,'x':s['name_x']+30,'y':top+s['name_offset']+s['name_height']//2})
 raise ValueError('search_contacts_boundary_unverified: possibly truncated results')

def unique_local(rows,recipient):
 matches=[r for r in rows if exact(r['text'])==exact(recipient)]
 if len(matches)!=1:raise ValueError('search_contact_missing_or_ambiguous')
 return matches[0]

def select(regions,recipient):
 if not isinstance(recipient,str) or not recipient.strip() or len(recipient)>80 or any(ord(c)<32 for c in recipient):raise ValueError('invalid recipient')
 start=time.perf_counter();layout=regions.check();s=layout.get('search')
 if not s:raise ValueError('needs_search_calibration')
 from wechat_regions import PROFILE
 profile=json.loads(PROFILE.read_text())
 # Opening the calibrated box must produce its green focus outline before editing.
 x,y,w,h=s['box'];regions.proxy.call('click',{'x':x+w//2,'y':y+h//2});time.sleep(.08)
 if not focused(regions.im(region(s['box']))):raise ValueError('search_box_not_focused: nothing typed')
 regions.proxy.call('key',{'shortcut':'ctrl+a'});regions.proxy.call('clipboard_write',{'text':recipient});regions.proxy.call('key',{'shortcut':'ctrl+v'});time.sleep(.08)
 if not focused(regions.im(region(s['box']))) or auto.copy_draft(regions.proxy)!=recipient:raise ValueError('search_query_mismatch')
 typed=time.perf_counter();deadline=typed+4;last_error=None
 while time.perf_counter()<deadline:
  try:
   if not popup_check(regions,layout,profile):raise ValueError('search_waiting_popup')
   panel=region(s['panel']);before=regions.im(panel)
   rows=read_contacts(regions,layout,frame=before)
   row=unique_local(rows,recipient)
   # Reuse OCR only when a fresh result panel is pixel-identical.
   time.sleep(.08)
   if regions.im(panel).tobytes()!=before.tobytes():raise ValueError('search_results_changing')
   popup_check(regions,layout,profile)
   regions.proxy.call('click',{'x':row['x'],'y':row['y']});break
  except ValueError as e:
   last_error=e
   if any(word in str(e) for word in ('ambiguous','unexpected','unreadable','boundary','main_window','layout_changed')):raise
   time.sleep(.1)
 else:raise ValueError(str(last_error or 'search_timeout'))
 clicked=time.perf_counter();deadline=clicked+3;stable=0
 while time.perf_counter()<deadline:
  time.sleep(.08)
  try:
   regions.check();title,c=regions.header()
   if exact(title)==exact(recipient) and c>=85:stable+=1
   else:stable=0
   if stable>=2:return {'search_ms':round((typed-start)*1000,2),'results_select_ms':round((clicked-typed)*1000,2),'wait_title_ms':round((time.perf_counter()-clicked)*1000,2),'title_confidence':c,'recipient':recipient,'selected_via':'local_contacts_search','submitted':False}
  except RuntimeError:stable=0
 raise ValueError('search_recipient_switch_timeout: nothing sent')
