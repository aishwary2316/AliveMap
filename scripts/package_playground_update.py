"""Build a private checksummed API-only update; never copies tunnel credentials."""
import base64,gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def prepare():
    original=json.loads(gzip.decompress(base64.b64decode((ROOT/'.local/permanent-payload.txt').read_text())))
    source=(ROOT/'mec/playground_api.py').read_text(encoding='utf-8')
    payload={'source':source,'sha256':hashlib.sha256(source.encode()).hexdigest(),
        'expected_sha256':hashlib.sha256(original['sources']['playground_api.py'].encode()).hexdigest()}
    program=(ROOT/'deployment/update_playground.py').read_text(encoding='utf-8')+'\nupdate('+repr(payload)+')\n'
    encoded=base64.b64encode(program.encode()).decode()
    (ROOT/'.local/playground-update-command.py').write_text("import base64\nexec(compile(base64.b64decode("+repr(encoded)+"),'<AliveMap API update>','exec'))\n",encoding='utf-8')
    print('Prepared API-only source update. No credentials included or printed.')

if __name__=='__main__':prepare()
