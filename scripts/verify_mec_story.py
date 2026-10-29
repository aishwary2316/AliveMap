"""Run one scoped SUMO story against the configured physical HTTPS MEC."""
import argparse,hashlib,json,time
from pathlib import Path
from types import SimpleNamespace
import httpx
from laptop.endpoint import endpoint
from laptop.map_launcher import available_packages
from laptop.playground_session import PlaygroundSession
from routing_core.maps import PackageMapProvider,read_json
from routing_core.playground import story_scene


def verify(output):
    url,headers=endpoint()
    provider=PackageMapProvider(available_packages()['delhi_urban'])
    scene=story_scene(provider,read_json(provider.path/provider.manifest['scenario']),'congestion')
    args=SimpleNamespace(gui=False,mec_mode='physical',mec_url=None,semantics_url=None,playground_url=None,
        map_package=provider.path,output=str(output/'run'),playground_scene=scene,incident_kind='none')
    with httpx.Client(base_url=url,headers=headers,timeout=6,trust_env=False) as check:
        def get(path):
            r=check.get(path);r.raise_for_status();return r.json()
        before=get('/health')
        if before.get('story_revision')!=1:raise RuntimeError('Deploy the managed story API update before physical verification')
        original={e['event_id']:hashlib.sha256(json.dumps(e,sort_keys=True).encode()).hexdigest() for e in get('/legacy/hazards')['events']}
        start=time.monotonic();session=PlaygroundSession(args)
        run_id=session.run_id
        result={}
        try:
            for _ in range(1000):
                session.step()
                if session.network['incidents'] and len(session.network['incidents'][0].get('reporters',[]))==2:break
            record=session.network['incidents'][0]
            assert set(record['reporters'])=={'scout-1','scout-2'}
            assert record['assessment']['confidence']=='corroborated'
            assert session.reroute_counts['cautious']>=1
            assert session.knowledge['cautious']
            affected=set(session.mapping[0]['edges'])
            route=session.frame()['vehicles']['cautious']['route']
            assert not affected.intersection(route)
            provider.validate_route(route)
            acks=[e for e in session.radio_events if e.get('stage')=='acknowledged']
            assert len({e['sim_time'] for e in acks})==2
            result={'endpoint':url,'https_certificate_verified':True,'backend':'physical MEC',
                'map':provider.manifest['map_id'],'scout_report_times':[e['sim_time'] for e in acks],
                'reporters':record['reporters'],'assessment':record['assessment'],
                'h3_cells':{k:len(v) for k,v in record['h3_cells'].items()},
                'receiver_actual_reroutes':session.reroute_counts['cautious'],
                'computed_route_valid':True,'computed_route_avoids_affected_edges':True,
                'elapsed_wall_seconds':round(time.monotonic()-start,3),'radio_path':'simulated tower coverage; actual 5G path not verified'}
        finally:session.close()
        after=get('/health')
        remaining={e['event_id']:hashlib.sha256(json.dumps(e,sort_keys=True).encode()).hexdigest()
            for e in get('/legacy/hazards')['events'] if run_id not in e['event_id']}
        assert remaining==original,'Unrelated original hazard records changed'
        assert after['experiments']==before['experiments'],'Scoped experiment cleanup did not restore the original count'
        result.update(scoped_cleanup_confirmed=True,unrelated_original_records_preserved=True,
            original_experiments=before['experiments'],remaining_experiments=after['experiments'])
        output.mkdir(parents=True,exist_ok=True)
        (output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('runs/physical-story-verification'))
    verify(parser.parse_args().output)
