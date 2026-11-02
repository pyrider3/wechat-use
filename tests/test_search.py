import json,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_search')
LAYOUT={'size':[1280,900],'search':{'panel':[130,128,555,745],'heading':[145,135,255,45],'row_top':181,'row_height':112,'max_rows':5,'name_x':225,'name_offset':35,'name_width':380,'name_height':48,'popup':{'x':86,'y':112,'width':644,'max_height':809}}}
class Fake:
 def __init__(self):self.proxy=self;self.calls=[]
 def im(self,_):return Image.new('RGB',(555,745),'white')
 def focus(self):return ('wechat','微信')
class SearchTests(unittest.TestCase):
 def test_local_section_only_stops_before_groups(self):
  with patch.object(m.auto,'ocr',side_effect=[('联系人',99),('noise',0),('fixture',99),('群聊',99)]):
   self.assertEqual([r['text'] for r in m.read_contacts(Fake(),LAYOUT)],['fixture'])
 def test_network_results_are_never_contacts(self):
  with patch.object(m.auto,'ocr',return_value=('网络查找微信号',99)):
   with self.assertRaisesRegex(ValueError,'no_local_contacts'):m.read_contacts(Fake(),LAYOUT)
 def test_low_confidence_row_refuses(self):
  with patch.object(m.auto,'ocr',side_effect=[('联系人',99),('noise',0),('fixture',70)]):
   with self.assertRaisesRegex(ValueError,'unreadable'):m.read_contacts(Fake(),LAYOUT)
 def test_missing_boundary_refuses_truncated_results(self):
  layout=json.loads(json.dumps(LAYOUT));layout['search']['max_rows']=1
  with patch.object(m.auto,'ocr',side_effect=[('联系人',99),('noise',0),('fixture',99)]):
   with self.assertRaisesRegex(ValueError,'boundary'):m.read_contacts(Fake(),layout)
 def test_unexpected_extra_window_refuses(self):
  geometry={'x':0,'y':0,'width':1265,'height':900}
  inv={'size':[1280,900],'windows':[{'id':1,'override_redirect':False,**geometry},{'id':2,'override_redirect':False,'x':1,'y':1,'width':10,'height':10}]}
  with patch.object(m,'inventory',return_value=inv):
   with self.assertRaisesRegex(ValueError,'unexpected_popup'):m.popup_check(Fake(),LAYOUT,{'geometry':geometry})
 def test_focus_requires_green_outline(self):self.assertFalse(m.focused(Image.new('RGB',(100,50),'white')))
 def test_workflow_routes_search_and_preserves_idempotency(self):
  w=load('wechat_workflow');p=Fake();p.fallback=lambda e:{'isError':True,'content':[]}
  item={'recipient':'fixture','text':'hello','operation_id':'search-fixture-0001'}
  with patch.object(m,'select',return_value={}) as search,patch.object(w,'select') as recent,patch.object(w.auto,'send',return_value={'content':[{'type':'text','text':'{"status":"ui_confirmed"}'}]}) as send:
   r=w.run(p,{'_search':True,'messages':[item]})
  self.assertFalse(r.get('isError'));search.assert_called_once();recent.assert_not_called();self.assertEqual(send.call_args.kwargs['recipient'],'fixture')

class SearchIdentityTests(unittest.TestCase):
 def test_duplicate_exact_remarks_refuse(self):
  with self.assertRaisesRegex(ValueError,'ambiguous'):m.unique_local([{'text':'fixture'},{'text':'fixture'}],'fixture')
 def test_case_difference_refuses(self):
  with self.assertRaisesRegex(ValueError,'ambiguous'):m.unique_local([{'text':'Fixture'}],'fixture')
 def test_partial_name_refuses(self):
  with self.assertRaisesRegex(ValueError,'ambiguous'):m.unique_local([{'text':'fixture other'}],'fixture')

class SearchRecoveryTests(unittest.TestCase):
 def test_known_popup_dismisses_once_then_rechecks_all_anchors(self):
  import tempfile,pathlib
  from wechat_regions import PROFILE
  class R(Fake):
   def check(self):
    self.calls.append(('check',{}))
    if len([x for x in self.calls if x[0]=='check'])==1:raise m.LayoutError('popup_or_extra_window')
    return LAYOUT
   def call(self,name,args):self.calls.append((name,args))
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile.json';p.write_text(json.dumps({'layout':LAYOUT,'geometry':{}}))
   with patch('wechat_regions.PROFILE',p),patch.object(m,'popup_check',return_value=True),patch.object(m.auto,'ocr',return_value=('联系人',96)):
    r=R();self.assertEqual(m.checked_layout(r),LAYOUT)
    self.assertEqual(r.calls,[('check',{}),('key',{'shortcut':'Escape'}),('check',{})])
 def test_unknown_popup_is_never_dismissed(self):
  import tempfile,pathlib
  r=Fake();r.check=lambda:(_ for _ in ()).throw(m.LayoutError('popup_or_extra_window'))
  r.call=lambda n,a:r.calls.append((n,a))
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile.json';p.write_text(json.dumps({'layout':LAYOUT,'geometry':{}}))
   with patch('wechat_regions.PROFILE',p),patch.object(m,'popup_check',side_effect=ValueError('search_unexpected_popup')):
    with self.assertRaisesRegex(ValueError,'unexpected_popup'):m.checked_layout(r)
  self.assertEqual(r.calls,[])
 def test_low_confidence_popup_heading_is_never_dismissed(self):
  import tempfile,pathlib
  r=Fake();r.check=lambda:(_ for _ in ()).throw(m.LayoutError('popup_or_extra_window'))
  r.call=lambda n,a:r.calls.append((n,a))
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile.json';p.write_text(json.dumps({'layout':LAYOUT,'geometry':{}}))
   with patch('wechat_regions.PROFILE',p),patch.object(m,'popup_check',return_value=True),patch.object(m.auto,'ocr',return_value=('联系人',70)):
    with self.assertRaisesRegex(ValueError,'unverified'):m.checked_layout(r)
  self.assertEqual(r.calls,[])
 def test_anchor_failure_after_popup_close_still_refuses(self):
  import tempfile,pathlib
  r=Fake();r.call=lambda n,a:r.calls.append((n,a))
  from unittest.mock import Mock
  r.check=Mock(side_effect=[m.LayoutError('popup_or_extra_window'),m.LayoutError('anchor_review_required')])
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile.json';p.write_text(json.dumps({'layout':LAYOUT,'geometry':{}}))
   with patch('wechat_regions.PROFILE',p),patch.object(m,'popup_check',return_value=True),patch.object(m.auto,'ocr',return_value=('联系人',96)):
    with self.assertRaisesRegex(m.LayoutError,'anchor_review'):m.checked_layout(r)
 def test_region_dimension_mismatch_refuses_before_ocr(self):
  with patch.object(m.auto,'ocr') as ocr:
   with self.assertRaisesRegex(ValueError,'frame_size'):m.read_contacts(Fake(),LAYOUT,Image.new('RGB',(100,50)))
   ocr.assert_not_called()
 def test_outside_crop_refuses_instead_of_padding_invented_pixels(self):
  import copy
  layout=copy.deepcopy(LAYOUT);layout['search']['heading']=[120,135,255,45]
  with self.assertRaisesRegex(ValueError,'crop_outside'):m.read_contacts(Fake(),layout)
 def test_boundary_keeps_top_of_section_label(self):
  # A section's first stroke lies above the old top+8 crop. Losing it would
  # make the next section look like a contact row and fail or select wrongly.
  frame=Image.new('RGB',(555,745),'white');top=181+112
  frame.putpixel((145-130,top-128),(0,0,0))
  seen=[]
  def ocr(im,psm):
   seen.append(im)
   if len(seen)==1:return ('联系人',99)
   if len(seen)==2:return ('noise',0)
   if len(seen)==3:return ('fixture',99)
   return ('更多',99) if b'\x00\x00\x00' in im.tobytes() else ('?',0)
  with patch.object(m.auto,'ocr',side_effect=ocr):
   self.assertEqual([r['text'] for r in m.read_contacts(Fake(),LAYOUT,frame)],['fixture'])

 def test_popup_unmap_delay_observed_without_second_escape(self):
  import tempfile,pathlib
  from unittest.mock import Mock
  r=Fake();r.call=lambda n,a:r.calls.append((n,a))
  r.check=Mock(side_effect=[m.LayoutError('popup_or_extra_window'),m.LayoutError('popup_or_extra_window'),LAYOUT])
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile.json';p.write_text(json.dumps({'layout':LAYOUT,'geometry':{}}))
   with patch('wechat_regions.PROFILE',p),patch.object(m,'popup_check',return_value=True),patch.object(m.auto,'ocr',return_value=('联系人',96)):
    self.assertEqual(m.checked_layout(r),LAYOUT)
  self.assertEqual(r.calls,[('key',{'shortcut':'Escape'})])
