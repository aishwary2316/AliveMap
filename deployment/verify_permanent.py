"""Controlled crash/recovery check of only the newly installed AliveMap API."""
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from uuid import uuid4


def verify():
    unit = Path('/etc/systemd/system/alivemap-playground.service')
    if not unit.read_text().startswith('# Managed by AliveMap permanent deployment\n'):
        raise RuntimeError('Target service is not the reviewed AliveMap deployment')
    key = Path('/etc/alivemap/api.env').read_text().strip().split('=', 1)[1]
    opener = build_opener(ProxyHandler({}))
    def request(path, method='GET', body=None, port=8768):
        data = json.dumps(body).encode() if body is not None else None
        outgoing = Request('http://127.0.0.1:%d%s'%(port,path), data=data, method=method,
                           headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with opener.open(outgoing, timeout=5) as response:
            return json.load(response)
    def status(name, prop):
        return subprocess.check_output(['systemctl','show',name,'-p',prop,'--value'], text=True).strip()
    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if request('/health')['experiments'] != 0:
        raise RuntimeError('Active AliveMap experiments exist; refusing disruptive test')
    original_events = request('/hazards', port=8765)['events']
    original_by_id = {e['event_id']:e for e in original_events}
    old_cloudflared = (status('cloudflared.service','MainPID'), status('cloudflared.service','ExecMainStartTimestampMonotonic'))
    # The system service's own config is never read for credentials or altered.
    import pwd
    owner = status('alivemap-playground.service','User')
    original_config = Path(pwd.getpwnam(owner).pw_dir)/'.cloudflared/config.yml'
    old_config_hash = digest(original_config) if original_config.exists() else None
    baseline = Path(pwd.getpwnam(owner).pw_dir)/'mec-av-poc/main.py'
    old_source_hash = digest(baseline)
    before_pid = status('alivemap-playground.service','MainPID')
    epoch = str(uuid4()); path='/v1/experiments/'+epoch
    request('/v1/experiments','POST',{'experiment_id':epoch,'map_id':'deployment-recovery-check',
                                     'bounds':[77.2,28.6,77.3,28.7],'towers':[]})
    geometry={'type':'Polygon','coordinates':[[[77.2498,28.6298],[77.2502,28.6298],[77.2502,28.6302],[77.2498,28.6302],[77.2498,28.6298]]]}
    report={'incident_id':'restart-check','vehicle_id':'operator','longitude':77.25,'latitude':28.63,
            'kind':'landslide','geometry':geometry,'event_version':1,'source_type':'synthetic_scenario'}
    receipt=request(path+'/observations','POST',report)['incident']
    checks={}
    try:
        subprocess.run(['systemctl','kill','--signal=SIGKILL','--kill-who=main','alivemap-playground.service'],check=True)
        for _ in range(50):
            try:
                if request('/health')['state_storage']=='sqlite':
                    break
            except OSError:
                pass
            time.sleep(.5)
        else:
            raise RuntimeError('Managed API did not automatically recover')
        checks['automatic_restart_after_controlled_crash']=status('alivemap-playground.service','MainPID') not in ('0', before_pid)
        after=request(path)
        checks['incident_and_receipt_survived_restart']=after['incidents'][0]==receipt
        checks['deduplication_survived_restart']=request(path+'/observations','POST',report)['deduplicated']
        request(path+'/observations','POST',{**report,'kind':'clear','event_version':2})
    finally:
        request(path,'DELETE')
    remaining=request('/hazards',port=8765)['events']
    by_id={e['event_id']:e for e in remaining}
    checks['preexisting_baseline_records_unchanged']=all(by_id.get(k)==v for k,v in original_by_id.items())
    checks['original_cloudflared_process_unchanged']=old_cloudflared==(status('cloudflared.service','MainPID'),status('cloudflared.service','ExecMainStartTimestampMonotonic'))
    checks['original_tunnel_configuration_unchanged']=old_config_hash==(digest(original_config) if original_config.exists() else None)
    checks['original_baseline_source_unchanged']=old_source_hash==digest(baseline)
    checks['test_experiment_cleaned']=request('/health')['experiments']==0
    for name in ('alivemap-baseline-watch.service','alivemap-playground.service','alivemap-tunnel.service'):
        checks[name+'_active']=status(name,'ActiveState')=='active'
        checks[name+'_enabled_for_boot']=status(name,'UnitFileState')=='enabled'
    if not all(checks.values()):
        raise RuntimeError('Recovery check failed: '+', '.join(k for k,v in checks.items() if not v))
    print(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'checks':checks,
                      'reboot_performed':False,'existing_applications_restarted':False}),flush=True)


if __name__=='__main__':
    verify()
