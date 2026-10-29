"""Prepare an ignored, secret-bearing payload for the approved scoped install."""
import base64
import gzip
import hashlib
import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_private_json(path):
    data = Path(path).read_bytes()
    return json.loads(data.decode('utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'))


def prepare():
    private = ROOT/'.local'
    inspected = read_private_json(private/'permanent-inspection.json')
    pending = private/'mec-endpoint.pending.json'
    if pending.exists():
        config = read_private_json(pending)
    else:
        config = {'url': 'https://alivemap.aishtrex.com', 'api_key': secrets.token_urlsafe(48)}
        pending.write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
    token = (private/'alivemap-tunnel.token').read_text(encoding='utf-8-sig').strip()
    expected = read_private_json(private/'alivemap-tunnel.json')
    token_data = json.loads(base64.b64decode(token))
    if token_data.get('t') != expected['tunnel_id'] or expected['hostname'] != 'alivemap.aishtrex.com':
        raise ValueError('Credential does not belong to the newly approved AliveMap tunnel')
    sources = {'playground_api.py': (ROOT/'mec/playground_api.py').read_text(encoding='utf-8'),
               'baseline_watch.py': (ROOT/'mec/baseline_watch.py').read_text(encoding='utf-8')}
    revision = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()[:20]
    payload = {'user': Path(inspected['home']).name, 'uid': inspected['uid'], 'revision': revision,
               'api_key': config['api_key'], 'tunnel_token': token, 'sources': sources,
               'units': {p.name.removesuffix('.in'): p.read_text(encoding='utf-8') for p in (ROOT/'deployment').glob('*.service.in')},
               'installer': (ROOT/'deployment/install_permanent.py').read_text(encoding='utf-8')}
    blob = gzip.compress(json.dumps(payload, separators=(',', ':')).encode(), mtime=0)
    (private/'permanent-payload.txt').write_text(base64.b64encode(blob).decode(), encoding='ascii')
    (private/'permanent-payload.sha256').write_text(hashlib.sha256(blob).hexdigest(), encoding='ascii')
    print('Prepared private AliveMap-only deployment payload. Credentials were not printed.')


if __name__ == '__main__':
    prepare()
