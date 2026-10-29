#!/usr/bin/python3
"""Native Wayland GTK viewer: fit locally, never resize the remote desktop."""
import pathlib,sys,json,os
CONFIG=pathlib.Path('@HOME@/.config/wbox-mcp/viewer/wayvnc.conf')
def credentials(path=CONFIG):
 # Read the existing local server credentials; never put secrets in argv/logs.
 values={}
 for line in path.read_text().splitlines():
  line=line.strip()
  if not line or line.startswith('#') or '=' not in line:continue
  key,value=line.split('=',1);values[key.strip()]=value.strip()
 if not values.get('password'):raise ValueError('本地查看器凭据缺失')
 return values

def configure(display):
 display.set_shared_flag(True)
 display.set_allow_resize(False)
 display.set_force_size(False)
 display.set_scaling(True)
 display.set_keep_aspect_ratio(True)
 display.set_smoothing(True)
 display.set_keyboard_grab(False)
 display.set_pointer_grab(False)
 # No client_cut_text or server-cut-text clipboard integration.

def enum_values(values):
 if hasattr(values,'n_values'):values=[values.get_nth(i) for i in range(values.n_values)]
 return [value.get_enum() if hasattr(value,'get_enum') else int(value) for value in values]

def main():
 import gi
 gi.require_version('Gtk','3.0');gi.require_version('GtkVnc','2.0');gi.require_version('GVnc','1.0')
 gi.require_version('Gdk','3.0')
 from gi.repository import GLib
 GLib.set_prgname('Vncviewer')
 from gi.repository import Gtk,Gdk,GtkVnc,GVnc,GObject
 Gdk.set_program_class('Vncviewer')
 secret=credentials()
 win=Gtk.Window(title='后台微信 · 独立桌面');win.set_default_size(760,820)
 box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0);win.add(box)
 status=Gtk.Label(label='正在连接后台微信……');status.set_margin_top(5);status.set_margin_bottom(5);box.pack_start(status,False,False,0)
 display=GtkVnc.Display();configure(display);box.pack_start(display,True,True,0)
 state={'connected':False,'remote_resize':False};state_path=pathlib.Path('@RUNTIME@/wbox-wechat-viewer-status.json')
 def record(**fields):
  state.update(fields)
  try:
   temp=state_path.with_suffix('.tmp');temp.write_text(json.dumps(state));temp.chmod(0o600);os.replace(temp,state_path)
  except OSError:pass
 connection=display.get_connection()
 # GTK-VNC prefers ARD auth, which crashes this local neatvnc build.
 # Keep the same password-protected VNC auth as the previous viewer.
 signal_id=GObject.signal_lookup('vnc-auth-choose-type',GVnc.Connection)
 GObject.signal_handlers_block_matched(connection,GObject.SignalMatchType.ID,signal_id,0,None,None,None)
 def choose_auth(conn,offered):
  if int(GVnc.ConnectionAuth.VNC) in enum_values(offered):conn.set_auth_type(GVnc.ConnectionAuth.VNC)
  else:status.set_text('本地查看服务不支持密码认证。');display.close()
 connection.connect('vnc-auth-choose-type',choose_auth)
 def auth(widget,requested):
  mapping={int(GVnc.ConnectionCredential.PASSWORD):secret['password'],int(GVnc.ConnectionCredential.USERNAME):secret.get('username',''),int(GVnc.ConnectionCredential.CLIENTNAME):'后台微信查看器'}
  for kind in enum_values(requested):
   if int(kind) not in mapping:
    status.set_text('不支持此认证方式，请检查本地查看服务。');widget.close();return
   widget.set_credential(int(kind),mapping[int(kind)])
 display.connect('vnc-auth-credential',auth)
 def initialized(*_):
  status.set_text('自动适应窗口 · 后台分辨率固定');record(connected=True,remote_size=[display.get_width(),display.get_height()],monitor_scale=display.get_scale_factor())
 display.connect('vnc-initialized',initialized)
 def allocation(widget,allocation):record(viewport=[allocation.width,allocation.height],monitor_scale=widget.get_scale_factor())
 display.connect('size-allocate',allocation)
 display.connect('notify::scale-factor',lambda *_:record(monitor_scale=display.get_scale_factor()))
 def timeout():
  if not state['connected']:display.close();status.set_text('连接超时，请关闭后重新打开“后台微信”。')
  return False
 GLib.timeout_add_seconds(15,timeout)
 display.connect('vnc-disconnected',lambda *_:status.set_text('连接已断开，关闭后重新打开“后台微信”即可。'))
 display.connect('vnc-error',lambda *_:status.set_text('查看连接失败，请关闭后重新打开“后台微信”。'))
 win.connect('destroy',lambda *_:Gtk.main_quit())
 win.show_all();display.grab_focus()
 if not display.open_host('127.0.0.1','15927'):status.set_text('无法连接查看服务，请关闭后重新打开。')
 Gtk.main()
if __name__=='__main__':
 try:main()
 except Exception as error:
  # Avoid emitting credential-bearing exceptions from third-party code.
  print('后台微信查看器未能打开，请确认已安装 python-gobject、gtk3、gtk-vnc。',file=sys.stderr);sys.exit(1)
