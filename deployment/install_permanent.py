"""Root-side, scoped installer. Invoked from a checksummed SSH payload only."""
import hashlib
import json
import os
import pwd
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

MARKER = '# Managed by AliveMap permanent deployment\n'
UNITS = ('alivemap-baseline-watch.service', 'alivemap-playground.service', 'alivemap-tunnel.service')
BASELINE_HASH = '45a06e0e9496df0cb2f9a80f330f6da998c787aba3df4c67d8d37407a13708c5'


def command(*args):
    return subprocess.run(args, check=True, stdout=sys.stderr, stderr=sys.stderr)


def health(port, key=None):
    headers = {'Authorization': 'Bearer '+key} if key else {}
    with build_opener(ProxyHandler({})).open(Request('http://127.0.0.1:%d/health'%port, headers=headers), timeout=4) as response:
        return json.load(response)


def write(path, content, mode=0o644, group=None):
    temporary = path.with_name(path.name+'.alivemap-new')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(content if isinstance(content, bytes) else content.encode('utf-8'))
            output.flush(); os.fsync(output.fileno())
        os.chmod(temporary, mode)
        if group is not None:
            os.chown(temporary, 0, group)
        os.replace(temporary, path)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise


def install(payload):
    if os.geteuid() != 0:
        raise RuntimeError('Administrator privilege is required for system services')
    account = pwd.getpwnam(payload['user'])
    if account.pw_uid != payload['uid'] or account.pw_uid == 0:
        raise RuntimeError('Remote account identity differs from inspected identity')
    home = Path(account.pw_dir)
    if not re.fullmatch(r'[0-9a-f]{20}', payload['revision']):
        raise RuntimeError('Invalid release identifier')
    baseline = home/'mec-av-poc'
    python = baseline/'.venv/bin/python'
    if hashlib.sha256((baseline/'main.py').read_bytes()).hexdigest() != BASELINE_HASH:
        raise RuntimeError('Original baseline source differs; no service changes made')
    if health(8765).get('service') != 'mec-av-poc':
        raise RuntimeError('Original API must be healthy before installation')
    cloudflared = shutil.which('cloudflared')
    if not cloudflared:
        raise RuntimeError('cloudflared binary is absent; original installation will not be changed')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,}', payload['api_key']):
        raise RuntimeError('Invalid application credential')
    unit_dir = Path('/etc/systemd/system')
    for name in UNITS:
        existing = unit_dir/name
        if existing.exists() and not existing.read_text().startswith(MARKER):
            raise RuntimeError('Service name already belongs to another deployment: '+name)
    with socket.socket() as probe:
        occupied = probe.connect_ex(('127.0.0.1', 8768)) == 0
    if occupied and not (unit_dir/'alivemap-playground.service').exists():
        raise RuntimeError('Port 8768 is already occupied; nothing stopped')
    app_dir = home/'alivemap-services'/payload['revision']
    for path in (app_dir, Path('/etc/alivemap'), Path('/var/lib/alivemap')):
        path.mkdir(parents=True, exist_ok=True)
    os.chmod('/etc/alivemap', 0o750); os.chown('/etc/alivemap', 0, account.pw_gid)
    os.chmod('/var/lib/alivemap', 0o700); os.chown('/var/lib/alivemap', account.pw_uid, account.pw_gid)
    for name, source in payload['sources'].items():
        if name not in ('playground_api.py', 'baseline_watch.py'):
            raise RuntimeError('Unexpected source filename')
        destination = app_dir/name
        if destination.exists() and destination.read_text() != source:
            raise RuntimeError('Content-addressed source changed; refusing overwrite')
        if not destination.exists():
            write(destination, source)
    env = Path('/etc/alivemap/api.env')
    if env.exists() and env.read_text() != 'ALIVEMAP_API_KEY='+payload['api_key']+'\n':
        raise RuntimeError('Existing AliveMap key differs; refusing implicit credential rotation')
    if not env.exists():
        write(env, 'ALIVEMAP_API_KEY='+payload['api_key']+'\n', 0o640, account.pw_gid)
    token_file = Path('/etc/alivemap/tunnel.token')
    if token_file.exists() and token_file.read_text() != payload['tunnel_token']:
        raise RuntimeError('Existing AliveMap tunnel token differs; refusing implicit rotation')
    if not token_file.exists():
        write(token_file, payload['tunnel_token'], 0o640, account.pw_gid)
    # An explicit, dedicated config prevents discovery of the existing tunnel's
    # ~/.cloudflared/config.yml, credentials or ingress routes.
    config_file = Path('/etc/alivemap/tunnel.yml')
    if config_file.exists() and config_file.read_text() != '{}\n':
        raise RuntimeError('Dedicated tunnel config already differs; refusing implicit changes')
    if not config_file.exists():
        write(config_file, '{}\n', 0o640, account.pw_gid)
    values = {'USER': account.pw_name, 'APP_DIR': str(app_dir), 'PYTHON': str(python),
              'BASELINE_DIR': str(baseline), 'WATCH_SCRIPT': str(app_dir/'baseline_watch.py'), 'CLOUDFLARED': cloudflared}
    if any(not re.fullmatch(r'[A-Za-z0-9_./-]+', v) for v in values.values()):
        raise RuntimeError('Unexpected characters in service paths; explicit escaping review required')
    for name in UNITS:
        template = payload['units'][name]
        for key, value in values.items():
            template = template.replace('@'+key+'@', value)
        if re.search(r'@[A-Z_]+@', template):
            raise RuntimeError('Unresolved service template')
        write(unit_dir/name, MARKER+template)
    command('systemd-analyze', 'verify', *(str(unit_dir/name) for name in UNITS))
    command('systemctl', 'daemon-reload')
    command('systemctl', 'enable', *UNITS)
    command('systemctl', 'start', 'alivemap-baseline-watch.service')
    command('systemctl', 'restart', 'alivemap-playground.service')
    ready = None
    for _ in range(30):
        try:
            ready = health(8768, payload['api_key'])
            if ready.get('state_storage') == 'sqlite' and ready.get('authentication') == 'bearer':
                break
        except OSError:
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError('Managed API failed readiness; inspect its dedicated journal')
    command('systemctl', 'restart', 'alivemap-tunnel.service')
    command('systemctl', 'is-active', *UNITS)
    command('systemctl', 'is-enabled', *UNITS)
    print(json.dumps({'installed': True, 'service_health': ready, 'units': list(UNITS),
                      'original_api_healthy': health(8765).get('status') == 'ok',
                      'existing_cloudflared_service_untouched': True}), flush=True)


if __name__ == '__main__':
    install(PAYLOAD)
