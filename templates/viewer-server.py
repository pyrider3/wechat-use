#!/usr/bin/python3
import json,os,pathlib
s=json.loads(pathlib.Path('/tmp/wbox_codex-background-wechat_state.json').read_text())
exe=pathlib.Path(f"/proc/{int(s['compositor_pid'])}/exe").resolve()
if exe.name!='labwc':raise SystemExit('后台微信桌面尚未运行，请先通过 wbox-wechat 启动。')
os.environ['WAYLAND_DISPLAY']=s['wayland_display']
os.execv('/usr/bin/wayvnc',['wayvnc','-C','@HOME@/.config/wbox-mcp/viewer/wayvnc.conf','-S','@RUNTIME@/wbox-wechat-wayvnc-control','-R','-f','20','-n','后台微信 · 独立桌面'])
