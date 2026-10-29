import tempfile,pathlib,unittest
from unittest.mock import Mock
from support import load
m=load('scaled-viewer')
class ScaledViewerTests(unittest.TestCase):
 def test_fit_never_resizes_remote_desktop(self):
  d=Mock();m.configure(d);d.set_scaling.assert_called_once_with(True);d.set_allow_resize.assert_called_once_with(False);d.set_force_size.assert_called_once_with(False);d.set_keep_aspect_ratio.assert_called_once_with(True)
 def test_does_not_send_clipboard_or_grab_user_keyboard(self):
  d=Mock();m.configure(d);d.client_cut_text.assert_not_called();d.set_keyboard_grab.assert_called_once_with(False);d.set_pointer_grab.assert_called_once_with(False)
 def test_credentials_from_local_file_only(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp)/'config';p.write_text('# comment\npassword=fake-test-secret\nusername=test\n')
   self.assertEqual(m.credentials(p)['password'],'fake-test-secret')
 def test_missing_password_fails_closed(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp)/'config';p.write_text('username=test\n')
   with self.assertRaises(ValueError):m.credentials(p)
 def test_gvalue_array_credentials_supported(self):
  values=Mock();values.n_values=2;values.get_nth.side_effect=[Mock(get_enum=lambda:0),Mock(get_enum=lambda:1)]
  self.assertEqual(m.enum_values(values),[0,1]);self.assertEqual(m.enum_values([0,2]),[0,2])
