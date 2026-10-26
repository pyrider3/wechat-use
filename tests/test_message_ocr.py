import unittest
from unittest.mock import patch
from PIL import Image
from support import load
m=load('auto_file_helper')
class MessageOCRTests(unittest.TestCase):
 def setUp(self):self.im=Image.new('RGB',(100,50),(160,240,150))
 def test_normal_high_confidence_fast_path(self):
  with patch.object(m,'ocr',return_value=('hello',90)) as o:
   self.assertEqual(m.message_ocr(self.im),('hello',90,'original'));self.assertEqual(o.call_count,1)
 def test_low_original_requires_agreement_and_high_second(self):
  with patch.object(m,'ocr',side_effect=[('hello',66),('hello',88),('hello',89),('hello',87)]):
   self.assertEqual(m.message_ocr(self.im),('hello',89,'multiview_agreement'))
 def test_disagreement_never_confirms(self):
  with patch.object(m,'ocr',side_effect=[('wrong',66),('hello',99),('different',99),('hello',99)]):
   self.assertLess(m.message_ocr(self.im)[1],75)
 def test_two_low_scores_never_confirm(self):
  with patch.object(m,'ocr',side_effect=[('hello',66),('hello',74.99),('hello',74),('hello',73)]):
   self.assertLess(m.message_ocr(self.im)[1],75)
 def test_empty_original_never_confirms(self):
  with patch.object(m,'ocr',side_effect=[('',0),('hello',99),('',0),('',0)]):
   self.assertLess(m.message_ocr(self.im)[1],75)
 def test_near_empty_original_never_confirms(self):
  with patch.object(m,'ocr',side_effect=[('hello',5),('hello',99),('',0),('',0)]):
   self.assertLess(m.message_ocr(self.im)[1],75)

 def test_wrong_low_original_recovers_with_two_high_views(self):
  with patch.object(m,'ocr',side_effect=[('wrong',33),('hello',66),('hello',88),('hello',81)]):
   self.assertEqual(m.message_ocr(self.im),('hello',88,'multiview_agreement'))
 def test_one_high_view_with_wrong_original_is_insufficient(self):
  with patch.object(m,'ocr',side_effect=[('wrong',33),('hello',66),('hello',88),('hello',60)]):
   self.assertLess(m.message_ocr(self.im)[1],75)
