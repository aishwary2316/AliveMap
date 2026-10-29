"""Guarded update of only the managed AliveMap API; run through its SSH helper."""
import hashlib,json,os,pwd,re,subprocess,time,sqlite3
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler

UNIT='alivemap-playground.service'
MARKER='# Managed by AliveMap permanent deployment\n'


def update(payload):
    if os.geteuid()!=0:raise RuntimeError('MEC sudo access is required')
    unit=Path('/etc/systemd/system')/UNIT
    content=unit.read_text()
    if not content.startswith(MARKER):raise RuntimeError('API service is not the managed AliveMap unit')
    fields=dict(line.split('=',1) for line in content.splitlines() if '=' in line)
    account=pwd.getpwnam(fields['User'])
    folder=Path(fields['WorkingDirectory']).resolve()
    if not folder.is_relative_to(Path(account.pw_dir)/'alivemap-services'):raise RuntimeError('Unexpected API source directory')
    source=folder/'playground_api.py'
    old=source.read_bytes();new=payload['source'].encode('utf-8')
    expected=payload['expected_sha256']
    if not re.fullmatch('[0-9a-f]{64}',expected) or hashlib.sha256(old).hexdigest()!=expected:
        raise RuntimeError('Running source differs from reviewed deployment; inspect it before updating')
    if hashlib.sha256(new).hexdigest()!=payload['sha256']:raise RuntimeError('Update checksum mismatch')
    compile(new,str(source),'exec')
    key=next(line.split('=',1)[1] for line in Path('/etc/alivemap/api.env').read_text().splitlines() if line.startswith('ALIVEMAP_API_KEY='))
    def health():
        req=Request('http://127.0.0.1:8768/health',headers={'Authorization':'Bearer '+key})
        with build_opener(ProxyHandler({})).open(req,timeout=3) as r:return json.load(r)
    before=health()
    if before.get('service')!='alivemap-playground-mec' or before.get('state_storage')!='sqlite':
        raise RuntimeError('Expected the managed persistent AliveMap API')
    database=Path('/var/lib/alivemap/playground.sqlite3')
    def state_ids():
        with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
            return {row[0] for row in db.execute('SELECT id FROM experiments')}
    backup=source.with_name('playground_api.py.before-'+expected[:12])
    if backup.exists() and backup.read_bytes()!=old:raise RuntimeError('Backup name already has other contents')
    backup.write_bytes(old)
    def replace(data):
        temporary=source.with_name('playground_api.py.update')
        with temporary.open('xb') as output:output.write(data);output.flush();os.fsync(output.fileno())
        os.chmod(temporary,0o644);os.replace(temporary,source)
    def restart():subprocess.run(['systemctl','restart',UNIT],check=True,timeout=20)
    try:
        subprocess.run(['systemctl','stop',UNIT],check=True,timeout=20)
        saved=state_ids()
        replace(new);restart()
        for _ in range(30):
            try:
                after=health()
                if after.get('story_revision')==1:
                    if not saved.issubset(state_ids()):raise RuntimeError('Stored experiment IDs were not recovered')
                    break
            except OSError:pass
            time.sleep(.3)
        else:raise RuntimeError('Updated API did not become ready')
    except Exception:
        replace(old);restart()
        raise
    print(json.dumps({'updated':True,'source_sha256':payload['sha256'],'health':after,
        'stored_experiments_preserved':True,'recovered_experiments':len(saved),
        'scope':'Only the managed AliveMap API source/process. No DNS, tunnel, baseline, Open5GS or MicroK8s changes.'}))
