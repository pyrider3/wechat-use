#!/usr/bin/env python3
"""Install user-level configuration. Does not install system packages or log in to WeChat."""
import argparse, json, os, pathlib, secrets, shutil, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parent
WBOX_REV = 'acbbf027430103ed90ee7d02350e84398a6fd425'

def render(text, home, install, runtime):
    for key, value in {'@HOME@':home, '@INSTALL@':install, '@RUNTIME@':runtime}.items():
        text = text.replace(key, str(value))
    return text

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true', help='Only check prerequisites; write nothing')
    ap.add_argument('--prefix', type=pathlib.Path, default=pathlib.Path.home()/'.local/share/wbox-mcp')
    ap.add_argument('--no-register', action='store_true', help='Do not register MCPs in Codex/Pi')
    args=ap.parse_args()
    home=pathlib.Path.home(); prefix=args.prefix.expanduser().resolve()
    runtime=pathlib.Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    if sys.platform!='linux':ap.error('Linux required')
    # Shell templates use fixed quoted paths. Reject characters that change shell syntax.
    for path in (home,prefix,runtime):
        if any(c in str(path) for c in ' \t\n\r\"\'`$\\'):ap.error('Paths containing whitespace or shell metacharacters are unsupported')
    required=['git','uv','labwc','grim','xdotool','xprop','setxkbmap','wlr-randr','xclip','wl-copy','wayvnc','vncviewer','vncpasswd','bwrap','dbus-run-session','systemctl','pactl','notify-send']
    missing=[x for x in required if not shutil.which(x)]
    if not pathlib.Path('/opt/wechat/wechat').is_file():missing.append('/opt/wechat/wechat (official Linux client)')
    if missing:
        print('Missing prerequisites:\n- '+'\n- '.join(missing));return 1
    print('Prerequisites found. WeChat runtime compatibility still needs a real login test.')
    if args.check:return 0
    # Never overwrite the existing installation or its live account state.
    if prefix.exists():ap.error(f'{prefix} already exists. Use a new --prefix; no files changed.')
    targets=[home/'.local/bin/wbox-mcp',home/'.local/bin/background-wechat-viewer',home/'.config/wbox-mcp/wechat/config.yaml',home/'.config/wbox-mcp/viewer/wayvnc.conf',home/'.config/systemd/user/wbox-wechat-silent.service',home/'.config/systemd/user/wbox-wechat-viewer.service',home/'.agents/skills/background-wechat/SKILL.md',home/'.local/share/applications/background-wechat-viewer.desktop']
    existing=[str(x) for x in targets if x.exists()]
    if existing:ap.error('Existing configuration would be overwritten: '+', '.join(existing))
    def run(*a,**kw):return subprocess.run([str(x) for x in a],check=True,**kw)
    prefix.mkdir(parents=True)
    src=prefix/'upstream'
    run('git','clone','https://github.com/quazardous/wbox-mcp.git',src)
    run('git','-C',src,'checkout','--detach',WBOX_REV)
    run('uv','venv',prefix/'.venv')
    run('uv','pip','install','--python',prefix/'.venv/bin/python',src)
    def write(source,dest,executable=False):
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(render((ROOT/source).read_text(),home,prefix,runtime))
        dest.chmod(0o700 if executable else 0o600)
    mapping={
      'viewer.py':(home/'.local/bin/background-wechat-viewer',True),
      'viewer-server.py':(prefix/'viewer-server.py',True),
      'manual-guard.py':(prefix/'manual-guard.py',True),
      'silent-audio.py':(prefix/'silent-audio.py',True),
      'start-wechat.sh':(home/'.config/wbox-mcp/wechat/start-wechat',True),
      'wbox-mcp.sh':(home/'.local/bin/wbox-mcp',True),
      'wbox-mcp-direct.sh':(prefix/'wbox-mcp-direct',True),
      'wechat.yaml':(home/'.config/wbox-mcp/wechat/config.yaml',False),
      'viewer.service':(home/'.config/systemd/user/wbox-wechat-viewer.service',False),
      'silent.service':(home/'.config/systemd/user/wbox-wechat-silent.service',False),
      'viewer.desktop':(home/'.local/share/applications/background-wechat-viewer.desktop',False)}
    for source,(dest,executable) in mapping.items():write('templates/'+source,dest,executable)
    (prefix/'wechat-profile').mkdir(mode=0o700)
    write('skills/background-wechat/SKILL.md',home/'.agents/skills/background-wechat/SKILL.md')
    viewer=home/'.config/wbox-mcp/viewer';viewer.mkdir(parents=True,exist_ok=True);viewer.chmod(0o700)
    password=secrets.token_urlsafe(6)
    conf=viewer/'wayvnc.conf';conf.write_text(f'address=127.0.0.1\nport=15927\nenable_auth=true\nrelax_encryption=true\nallow_broken_crypto=true\nusername=local\npassword={password}\n');conf.chmod(0o600)
    result=run('vncpasswd','-f',input=(password+'\n').encode(),stdout=subprocess.PIPE)
    secret=viewer/'passwd';secret.write_bytes(result.stdout);secret.chmod(0o600)
    run('systemctl','--user','daemon-reload')
    run('systemctl','--user','enable','--now','wbox-wechat-silent.service')
    if not args.no_register:
        for client in ('codex','pi'):
            if not shutil.which(client):continue
            extra=['--exposure','direct'] if client=='pi' else []
            run(client,'mcp','add','wbox-wechat',*extra,'--',home/'.local/bin/wbox-mcp','serve','--mcp-dir',home/'.config/wbox-mcp/wechat')
            niri=shutil.which('niri-computer-use')
            if niri:run(client,'mcp','add','niri-computer-use',*extra,'--',niri,'serve')
    print('Installed. Start wbox-wechat with MCP launch, screenshot the login QR, and log in yourself.')
    print('Open 后台微信 from the application menu. Pi: /reload. Codex: reconnect/restart.')
    return 0
if __name__=='__main__':sys.exit(main())
