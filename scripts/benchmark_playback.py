"""Compare per-step HTTPS telemetry with paced telemetry using actual SUMO.

Both runs use the same scene without anomalies and clean up their own MEC
experiments. This measures maximum stepping throughput, not UI frame rate.
"""
import argparse
import json
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from laptop.geo_session import GeoSession
from laptop.map_launcher import available_packages
from laptop.playground_session import PlaygroundSession
from routing_core.maps import PackageMapProvider, read_json
from routing_core.playground import example_scene


def benchmark(url, steps=80):
    provider=PackageMapProvider(available_packages()['delhi_urban'])
    scene=example_scene(provider,read_json(provider.path/provider.manifest['scenario']))
    scene['anomalies']=[]
    results={}
    for mode in ('per_step_telemetry','paced_telemetry'):
        args=SimpleNamespace(gui=False,mec_url=None,semantics_url=None,playground_url=url,mec_mode='physical',
            map_package=provider.path,_prepared_provider=provider,output=Path('runs/playback-benchmark'),
            playground_scene=deepcopy(scene),incident_kind='none')
        session=PlaygroundSession(args)
        count=[0]
        original=session.client.tick
        def tick(*a,**k):
            count[0]+=1
            return original(*a,**k)
        session.client.tick=tick
        started=time.perf_counter()
        initial=session.sim_time
        try:
            for _ in range(steps):
                if mode=='per_step_telemetry':
                    GeoSession.step(session)
                    session.refresh()
                    session.detect()
                else:
                    session.step()
            elapsed=time.perf_counter()-started
            results[mode]={'wall_seconds':round(elapsed,3),'simulated_seconds':session.sim_time-initial,
                'actual_speed':round((session.sim_time-initial)/elapsed,2),'telemetry_requests':count[0],
                'collisions':session.connection.simulation.getCollidingVehiclesNumber(),
                'teleports':session.connection.simulation.getStartingTeleportNumber()}
        finally:
            session.close()
    results['throughput_ratio']=round(results['paced_telemetry']['actual_speed']/results['per_step_telemetry']['actual_speed'],2)
    return {'recorded_at':datetime.now(timezone.utc).isoformat(),'backend':'physical MEC HTTPS',
        'map':'delhi_urban','steps_per_run':steps,'anomalies':0,'scope':'headless stepping; not GPU or UI FPS',**results}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default=None)
    parser.add_argument('--steps',type=int,default=80)
    parser.add_argument('--evidence',default='evidence/deployment/playback-benchmark.json')
    args=parser.parse_args()
    result=benchmark(args.url,args.steps)
    path=Path(args.evidence);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
