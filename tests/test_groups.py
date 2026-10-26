import json,pathlib,tempfile,unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('wechat_groups')
def row(text,y,confidence=.99):return {'text':text,'confidence':confidence,'bounds':[20,y,300,25]}
class GroupTests(unittest.TestCase):
 def test_excludes_network_results(self):
  rows=[row('群聊',10),row('2026协会',100),row('搜索网络结果',200),row('网络协会',250)]
  self.assertEqual([r['text'] for r in m.group_rows(rows,'协会')],['2026协会'])
 def test_section_boundary_required(self):
  with self.assertRaisesRegex(ValueError,'incomplete'):m.group_rows([row('群聊',10),row('协会',100)],'协会')
 def test_more_results_refuse(self):
  with self.assertRaisesRegex(ValueError,'incomplete'):m.group_rows([row('群聊',10),row('协会',100),row('查看更多群聊',150),row('更多',200)],'协会')
 def test_duplicate_names_refuse(self):
  with self.assertRaisesRegex(ValueError,'duplicate'):m.group_rows([row('群聊',10),row('协会',100),row('协会',150),row('更多',200)],'协会')
 def test_title_requires_exact_group(self):
  with self.assertRaisesRegex(ValueError,'mismatch'):m.parse_title([row('另一个群(149)',10)],'目标群')
 def test_count_parsing_and_confidence(self):
  self.assertEqual(m.parse_title([row('2026协会（262）',10)],'2026协会'),(262,.99))
  with self.assertRaisesRegex(ValueError,'unreliable'):m.parse_title([row('2026协会(262)',10,.8)],'2026协会')
 def test_batch_only_clicks_and_returns_verified_counts(self):
  class Fake:
   def __init__(self):self.proxy=self;self.calls=[]
   def check(self):return {'search':{'panel':[130,128,555,745]},'group_header':'550,75 485x50'}
   def im(self,_):return Image.new('RGB',(10,10),'white')
   def call(self,n,a):self.calls.append((n,a))
   def fallback(self,e):return {'isError':True,'content':[{'type':'text','text':str(e)}]}
  r=Fake();reader=m.GroupReader(r);reader.ocr=object();rows=[row('一协会',100),row('二协会',200)];frame=r.im('')
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t)/'profile';p.write_text('{}')
   with patch.object(m,'PROFILE',p),patch.object(reader,'search',return_value=(rows,frame)),patch.object(m,'popup_check',return_value=True),patch.object(reader,'count',side_effect=[(262,.99),(158,.99)]):result=reader.run({'query':'协会'})
  self.assertFalse(result.get('isError'));self.assertTrue(all(n=='click' for n,a in r.calls));self.assertEqual([g['members'] for g in json.loads(result['content'][0]['text'])['groups']],[262,158])

 def test_transient_incomplete_search_waits_for_full_section(self):
  from unittest.mock import Mock
  class Fake:
   def __init__(self):self.proxy=self;self.calls=[]
   def check(self):return {}
   def im(self,_):return Image.new('RGB',(10,10),'white')
   def call(self,n,a):self.calls.append((n,a))
  fake=Fake();reader=m.GroupReader(fake);reader.ocr=Mock();reader.ocr.read.return_value=[]
  layout={'search':{'box':[130,77,310,46],'panel':[130,128,555,745]}};rows=[row('协会',100)]
  with patch.object(m,'focused',return_value=True),patch.object(m.auto,'copy_draft',return_value='协会'),patch.object(m,'popup_check',return_value=True),patch.object(m,'group_rows',side_effect=[ValueError('group_results_incomplete'),rows]),patch.object(m.time,'sleep'):
   result,_=reader.search('协会',layout,{})
  self.assertEqual(result,rows);self.assertFalse(any(n=='key' and a.get('shortcut')=='Return' for n,a in fake.calls))
