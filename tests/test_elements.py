import json,tempfile,pathlib,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_elements')
class Fake:
 def __init__(self):self.proxy=self;self.actions=[]
 def check(self):return {'size':[1280,900],'header':'550,75 380x48','draft':'550,675 680x125','messages':'540,145 700x500','input':[740,700],'search':{'box':[130,77,310,46]}}
 def capture(self):return {'frame':'fake'}
 def fallback(self,e):return {'isError':True,'content':[{'type':'text','text':str(e)}]}
class ElementTests(unittest.TestCase):
 def test_cache_is_exact_pixel_and_kind_specific(self):
  x=m.ElementMap(Fake());calls=[]
  def read(im):calls.append(1);return 'fixture'
  white=Image.new('RGB',(10,10),'white');black=Image.new('RGB',(10,10),'black')
  self.assertEqual(x.cached(white,'title',read)[1],1);self.assertEqual(x.cached(white,'title',read)[1],0)
  x.cached(black,'title',read);x.cached(white,'draft',read);self.assertEqual(len(calls),3)
 def test_map_returns_coordinates_and_no_image_or_empty_draft_claim(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile';p.write_text('{"anchors":[]}');r=Fake();em=m.ElementMap(r)
   def ocr(im,psm):return ('fixture',99) if psm==7 else ('',0)
   rows=[{'text':'unique','confidence':99,'x':10,'y':20,'width':100,'height':25},{'text':'uncertain','confidence':20,'x':10,'y':80,'width':100,'height':25}]
   with patch.object(m,'PROFILE',p),patch.object(m.auto,'image',return_value=Image.new('RGB',(1280,900),'white')),patch.object(m.auto,'ocr',side_effect=ocr),patch.object(m.auto,'last_bubble',return_value=None),patch.object(m,'lines',return_value=rows):
    result=em.run();data=json.loads(result['content'][0]['text'])
   self.assertFalse(result.get('isError'));self.assertTrue(all(c['type']=='text' for c in result['content']));self.assertFalse(data['image_returned'])
   row=next(e for e in data['elements'] if e['role']=='recent_chat_name');self.assertEqual(row['bounds'],[208,165,100,25]);self.assertNotIn('uncertain',[e['text'] for e in data['elements']]);self.assertNotIn('draft_empty',data);self.assertFalse(r.actions)
 def test_unknown_layout_falls_back(self):
  r=Fake();r.check=lambda:(_ for _ in ()).throw(ValueError('layout_changed'));out=m.ElementMap(r).run();self.assertTrue(out['isError']);self.assertIn('layout_changed',out['content'][0]['text'])
 def test_low_confidence_title_refuses(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile';p.write_text('{"anchors":[]}')
   with patch.object(m,'PROFILE',p),patch.object(m.auto,'image',return_value=Image.new('RGB',(1280,900),'white')),patch.object(m.auto,'ocr',return_value=('guess',60)),patch.object(m.auto,'last_bubble',return_value=None),patch.object(m,'lines',return_value=[]):
    self.assertTrue(m.ElementMap(Fake()).run()['isError'])

class ElementToggleTests(unittest.TestCase):
 def test_disabled_tool_never_reads_screen(self):
  guard=load('manual-guard')
  with tempfile.TemporaryDirectory() as t:
   flag=pathlib.Path(t)/'disabled';flag.touch()
   with patch.object(guard,'ELEMENTS_DISABLED',flag):
    proxy=guard.Proxy.__new__(guard.Proxy);result=proxy.fast('inspect_ui_elements',{})
   self.assertTrue(result['isError']);self.assertFalse(hasattr(proxy,'regions'))

class ElementSelectionTests(unittest.TestCase):
 def setup_case(self,text='fixture',changed=False):
  import hashlib,time
  w=load('wechat_workflow');white=Image.new('RGB',(100,50),'white')
  class Map:
   last_contacts=('1,1 100x50',hashlib.sha256(white.tobytes()).hexdigest())
   def inspect(self):return {'captured_at_unix':time.time(),'frame_id':'frame','elements':[{'id':'e3','role':'recent_chat_name','text':text,'source':'ocr','confidence':99,'center':[210,200]}]}
  class R:
   def __init__(self):self.proxy=self;self.element_map=Map();self.calls=[]
   def check(self):return {}
   def im(self,_):return Image.new('RGB',(100,50),'black') if changed else white
   def call(self,n,a):self.calls.append((n,a))
   def header(self):return 'fixture',99
  return w,R()
 def test_uses_map_coordinates_and_verifies_title(self):
  w,r=self.setup_case()
  with patch.object(w.time,'sleep'):out=w.select_element(r,'fixture')
  self.assertEqual(r.calls,[('click',{'x':210,'y':200})]);self.assertEqual(out['selected_via'],'text_element_map')
 def test_wrong_name_never_clicks(self):
  w,r=self.setup_case(text='other')
  with self.assertRaisesRegex(ValueError,'missing_or_ambiguous'):w.select_element(r,'fixture')
  self.assertFalse(r.calls)
 def test_changed_contact_pixels_never_clicks(self):
  w,r=self.setup_case(changed=True)
  with self.assertRaisesRegex(ValueError,'contacts_changed'):w.select_element(r,'fixture')
  self.assertFalse(r.calls)
 def test_expired_map_never_clicks(self):
  w,r=self.setup_case();old=r.element_map.inspect;r.element_map.inspect=lambda:{**old(),'captured_at_unix':0}
  with self.assertRaisesRegex(ValueError,'expired'):w.select_element(r,'fixture')
  self.assertFalse(r.calls)

 def test_nonvisible_contact_uses_guarded_search(self):
  w,r=self.setup_case(text='other');old=r.element_map.inspect
  r.element_map.inspect=lambda:{**old(),'elements':old()['elements']+[{'role':'search_field','source':'reviewed_layout'}]}
  search=load('wechat_search')
  with patch.object(search,'select',return_value={'selected_via':'local_contacts_search','submitted':False}) as select:
   out=w.select_element(r,'fixture')
  select.assert_called_once_with(r,'fixture');self.assertFalse(r.calls);self.assertEqual(out['selected_via'],'text_element_map_then_local_search')

 def test_already_open_contact_is_not_clicked_again(self):
  w,r=self.setup_case();old=r.element_map.inspect
  r.element_map.inspect=lambda:{**old(),'elements':old()['elements']+[{'role':'chat_title','text':'fixture','confidence':99}]}
  with patch.object(w.time,'sleep'):out=w.select_element(r,'fixture')
  self.assertFalse(r.calls);self.assertEqual(out['selected_via'],'text_element_map')
