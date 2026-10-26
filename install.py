#!/usr/bin/env python3
"""Install or update wechat-use user-level helpers without replacing account data."""
import argparse, ctypes.util, hashlib, json, os, pathlib, secrets, shutil, subprocess, sys, time, urllib.request
ROOT = pathlib.Path(__file__).resolve().parent
WBOX_REV = 'acbbf027430103ed90ee7d02350e84398a6fd425'
TESSDATA_REV = '87416418657359cb625c412a48b6e1d6d41c29bd'
MODELS = {
    'chi_sim': 'a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730',
    'eng': '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2',
}

def render(text, home, install, runtime):
    for key, value in {'@HOME@': home, '@INSTALL@': install, '@RUNTIME@': runtime}.items():
        text = text.replace(key, str(value))
    return text

def targets(home, prefix):
    return {
        'viewer.py': (home / '.local/bin/background-wechat-viewer', True),
        'viewer-server.py': (prefix / 'viewer-server.py', True),
        'manual-guard.py': (prefix / 'manual-guard.py', True),
        'auto_file_helper.py': (prefix / 'auto_file_helper.py', False),
        'wechat_regions.py': (prefix / 'wechat_regions.py', False),
        'silent-audio.py': (prefix / 'silent-audio.py', True),
        'start-wechat.sh': (home / '.config/wbox-mcp/wechat/start-wechat', True),
        'wbox-mcp.sh': (home / '.local/bin/wbox-mcp', True),
        'wbox-mcp-direct.sh': (prefix / 'wbox-mcp-direct', True),
        'viewer.service': (home / '.config/systemd/user/wbox-wechat-viewer.service', False),
        'silent.service': (home / '.config/systemd/user/wbox-wechat-silent.service', False),
        'viewer.desktop': (home / '.local/share/applications/background-wechat-viewer.desktop', False),
    }

def ensure_model(directory, name, digest):
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / (name + '.traineddata')
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == digest:
        return
    url = f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{TESSDATA_REV}/{name}.traineddata'
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError(f'OCR model checksum mismatch: {name}; nothing replaced')
    temporary = dest.with_suffix('.download')
    temporary.write_bytes(data)
    temporary.replace(dest)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true', help='Only check prerequisites; write nothing')
    ap.add_argument('--update', action='store_true', help='Update an existing managed installation; preserve config, profiles and credentials')
    ap.add_argument('--prefix', type=pathlib.Path, default=pathlib.Path.home() / '.local/share/wbox-mcp')
    ap.add_argument('--no-register', action='store_true', help='Do not register MCPs in Codex/Pi')
    args = ap.parse_args()
    home = pathlib.Path.home()
    prefix = args.prefix.expanduser().resolve()
    runtime = pathlib.Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    if sys.platform != 'linux':
        ap.error('Linux required')
    for path in (home, prefix, runtime):
        if any(c in str(path) for c in ' \t\n\r\"\'`$\\'):
            ap.error('Paths containing whitespace or shell metacharacters are unsupported')
    required = ['git', 'uv', 'labwc', 'grim', 'Xwayland', 'xdotool', 'xprop', 'setxkbmap', 'wlr-randr', 'xclip', 'wl-copy', 'wayvnc', 'vncviewer', 'vncpasswd', 'bwrap', 'dbus-run-session', 'systemctl', 'pactl', 'notify-send', 'tesseract']
    missing = [x for x in required if not shutil.which(x)]
    if not ctypes.util.find_library('X11'):
        missing.append('libX11')
    if not pathlib.Path('/opt/wechat/wechat').is_file():
        missing.append('/opt/wechat/wechat (official Linux client)')
    if missing:
        print('Missing prerequisites:\n- ' + '\n- '.join(missing))
        return 1
    print('Prerequisites found. Cross-machine WeChat compatibility still requires a real login test.')
    if args.check:
        return 0
    mapping = targets(home, prefix)
    config = home / '.config/wbox-mcp/wechat/config.yaml'
    skill = home / '.agents/skills/background-wechat/SKILL.md'
    viewer = home / '.config/wbox-mcp/viewer'
    if args.update:
        if not (prefix / '.venv/bin/wbox-mcp').is_file() or not (prefix / 'manual-guard.py').is_file() or not config.is_file():
            ap.error('--update requires an existing wechat-use/wbox-mcp installation and its config')
        if not all((viewer / name).is_file() for name in ('wayvnc.conf', 'passwd')):
            ap.error('Viewer credentials missing; restore them before updating')
        # The helper paths must agree with the existing config to avoid switching profiles silently.
        if str(prefix / 'wechat-profile') not in (home / '.config/wbox-mcp/wechat/start-wechat').read_text():
            ap.error('Existing launcher belongs to a different prefix; use its original --prefix')
    else:
        paths = [prefix, config, skill, viewer / 'wayvnc.conf', viewer / 'passwd', *(dest for dest, _ in mapping.values())]
        existing = [str(p) for p in paths if p.exists()]
        if existing:
            ap.error('Existing installation/configuration found. Use --update for managed installs; nothing overwritten: ' + ', '.join(existing))
    def run(*command, **kw):
        return subprocess.run([str(x) for x in command], check=True, **kw)
    prefix.mkdir(parents=True, exist_ok=True)
    if not args.update:
        source = prefix / 'upstream'
        run('git', 'clone', 'https://github.com/quazardous/wbox-mcp.git', source)
        run('git', '-C', source, 'checkout', '--detach', WBOX_REV)
        run('uv', 'venv', prefix / '.venv')
        run('uv', 'pip', 'install', '--python', prefix / '.venv/bin/python', source)
    run('uv', 'pip', 'install', '--python', prefix / '.venv/bin/python', 'Pillow>=10,<14')
    for name, digest in MODELS.items():
        ensure_model(prefix / 'tessdata', name, digest)
    backup = prefix / 'backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)) if args.update else None
    def write(source, dest, executable=False):
        if backup and dest.exists():
            relative = dest.relative_to(home) if dest.is_relative_to(home) else pathlib.Path('prefix') / dest.relative_to(prefix)
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
        dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = dest.with_name(dest.name + '.wechat-use-new')
        temporary.write_text(render((ROOT / source).read_text(), home, prefix, runtime))
        temporary.chmod(0o700 if executable else 0o600)
        temporary.replace(dest)
    for source, (dest, executable) in mapping.items():
        write('templates/' + source, dest, executable)
    write('skills/background-wechat/SKILL.md', skill)
    example = home / '.config/wbox-mcp/wechat/auto-layout.example.json'
    write('templates/auto-layout.example.json', example)
    if not args.update:
        write('templates/wechat.yaml', config)
        (prefix / 'wechat-profile').mkdir(mode=0o700)
        viewer.mkdir(parents=True, exist_ok=True)
        viewer.chmod(0o700)
        password = secrets.token_urlsafe(6)
        conf = viewer / 'wayvnc.conf'
        conf.write_text(f'address=127.0.0.1\nport=15927\nenable_auth=true\nrelax_encryption=true\nallow_broken_crypto=true\nusername=local\npassword={password}\n')
        conf.chmod(0o600)
        result = run('vncpasswd', '-f', input=(password + '\n').encode(), stdout=subprocess.PIPE)
        secret = viewer / 'passwd'
        secret.write_bytes(result.stdout)
        secret.chmod(0o600)
    # Preserve existing config.yaml, calibrated layout, account data and credentials on updates.
    run('systemctl', '--user', 'daemon-reload')
    run('systemctl', '--user', 'enable', '--now', 'wbox-wechat-silent.service')
    if not args.no_register:
        for client in ('codex', 'pi'):
            if not shutil.which(client):
                continue
            extra = ['--exposure', 'direct'] if client == 'pi' else []
            run(client, 'mcp', 'add', 'wbox-wechat', *extra, '--', home / '.local/bin/wbox-mcp', 'serve', '--mcp-dir', home / '.config/wbox-mcp/wechat')
            niri = shutil.which('niri-computer-use')
            if niri:
                run(client, 'mcp', 'add', 'niri-computer-use', *extra, '--', niri, 'serve')
    if backup:
        print('Updated helpers; backup:', backup)
    print('Pi: /reload. Codex: reconnect/restart MCP. Running WeChat was not stopped.')
    print('For first setup, launch with MCP, inspect the login QR and log in yourself. Calibrate regions from a fresh screenshot.')
    return 0
if __name__ == '__main__':
    sys.exit(main())
