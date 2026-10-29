import base64
import gzip
import json
from pathlib import Path

from scripts import package_permanent

ROOT=Path(__file__).resolve().parents[1]


def test_utf16_inspection_payload_is_scoped_and_credentials_are_not_printed(tmp_path,monkeypatch,capsys):
    private=tmp_path/'.local';private.mkdir()
    (private/'permanent-inspection.json').write_text(json.dumps({'home':'/home/test-user','uid':1000}),encoding='utf-16')
    (private/'alivemap-tunnel.json').write_text(json.dumps({'tunnel_id':'new-test-tunnel','hostname':'alivemap.aishtrex.com'}))
    token=base64.b64encode(json.dumps({'t':'new-test-tunnel','s':'test-only-secret'}).encode()).decode()
    (private/'alivemap-tunnel.token').write_text(token)
    for relative in ('mec/playground_api.py','mec/baseline_watch.py','deployment/install_permanent.py',
                     'deployment/alivemap-playground.service.in','deployment/alivemap-baseline-watch.service.in','deployment/alivemap-tunnel.service.in'):
        target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/relative).read_bytes())
    monkeypatch.setattr(package_permanent,'ROOT',tmp_path)
    package_permanent.prepare()
    payload=json.loads(gzip.decompress(base64.b64decode((private/'permanent-payload.txt').read_bytes())))
    assert set(payload['units'])=={'alivemap-playground.service','alivemap-baseline-watch.service','alivemap-tunnel.service'}
    assert '--config /etc/alivemap/tunnel.yml' in payload['units']['alivemap-tunnel.service']
    output=capsys.readouterr().out
    assert payload['api_key'] not in output
    assert token not in output
    assert payload['user']=='test-user'
    compile(payload['installer'],'permanent-installer','exec')
