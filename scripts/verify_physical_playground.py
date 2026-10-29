"""Exercise actual SUMO against the authenticated physical playground forward.

Run from the repository: python -m scripts.verify_physical_playground
Writes its own run logs and a shareable aggregate result; never embeds SSH data.
"""
import argparse
import json
import time
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx

from laptop.map_launcher import available_packages
from laptop.playground_session import PlaygroundSession
from laptop.geo_session import GeoSession
from routing_core.maps import PackageMapProvider, read_json
from routing_core.playground import example_scene

ROOT = Path(__file__).resolve().parents[1]


def verify(url, map_id):
    packages = available_packages()
    provider = PackageMapProvider(packages[map_id])
    scene = example_scene(provider, read_json(provider.path/provider.manifest['scenario']))
    scene['vehicles']['standard']['role'] = 'offline'
    checks = {}
    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise AssertionError(name)
        print('PASS '+name, flush=True)
    args = SimpleNamespace(gui=False, mec_url='http://127.0.0.1:18765', semantics_url=None,
                           playground_url=url, map_package=provider.path, output=ROOT/'runs/physical-playground',
                           playground_scene=scene, incident_kind='none')
    def emit(kind, **data):
        if kind in ('ready', 'radio'):
            print(data.get('message', kind), flush=True)
    with httpx.Client(base_url=url, trust_env=False, timeout=10) as observer:
        health = observer.get('/health'); health.raise_for_status()
        initial_count = health.json()['experiments']
        session = PlaygroundSession(args, emit)
        epoch = session.run_id
        result = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'map_id': map_id,
                  'backend': 'physical MEC over SSH HTTP forwarding', 'run_id': epoch,
                  'service': health.json(), 'rf_ue_upf_verified': False}
        try:
            check('no incident published before perception', not session.network['incidents'])
            last = time.monotonic()
            last_radio_time = session.sim_time
            for _ in range(3200):
                if 'vehicle uploaded real MEC receipt' not in checks:
                    session.step()
                else:
                    # This fixture has one acknowledged, immutable anomaly until
                    # arrivals. Exercise driving using each agent's received cache;
                    # poll every 10 simulation seconds rather than every SUMO tick.
                    GeoSession.step(session)
                    if session.sim_time-last_radio_time >= 10:
                        session.refresh()
                        last_radio_time = session.sim_time
                if session.network['incidents']:
                    record = session.network['incidents'][0]
                    if 'vehicle uploaded real MEC receipt' not in checks:
                        check('vehicle uploaded real MEC receipt', record['reporter'] != 'operator' and bool(record['receipt']['h3_cell']))
                        check('MEC computed affected H3 r8 and r10', bool(record['h3_cells']['8']) and bool(record['h3_cells']['10']))
                        check('connected receiver informed', bool(session.knowledge['cautious']))
                        check('offline vehicle received no fact', not session.knowledge['standard'])
                        result['first_report'] = {'vehicle': record['reporter'], 'sim_time': record['sim_time'],
                                                  'source_type': record['observation']['source_type'],
                                                  'h3_counts': {r: len(v) for r, v in record['h3_cells'].items()}}
                if time.monotonic()-last > 20:
                    print(f'Progress: simulation {session.sim_time:.1f}s; arrived {sorted(session.arrived)}', flush=True)
                    last = time.monotonic()
                if session.arrived == set(session.fleet):
                    break
            affected = set(provider.edges_intersecting_geometry(scene['anomalies'][0]['geometry']))
            check('all vehicles arrived without collision or teleport', session.arrived == set(session.fleet))
            check('receiver computed and drove a detour', session.reroute_counts['cautious'] > 0 and not affected.intersection(session.driven_edges['cautious']))
            check('offline vehicle retained route and traversed anomaly roads', session.reroute_counts['standard'] == 0 and bool(affected.intersection(session.driven_edges['standard'])))
            result.update(sim_time=session.sim_time, reroute_counts=session.reroute_counts.copy(), arrival_times=session.arrival_times.copy())
            result['driving_phase_poll_interval_sim_s'] = 10
            session.refresh()
            second = {**deepcopy(scene['anomalies'][0]), 'id': 'operator-second'}
            session.edit('anomaly', second)
            session.edit('publish', {'id': second['id']})
            session.edit('clear', {'id': scene['anomalies'][0]['id']})
            records = {r['id']: r for r in session.network['incidents']}
            check('selected clearance leaves other incident active', records[scene['anomalies'][0]['id']]['status'] == 'cleared' and records[second['id']]['status'] == 'active')
            check('original API acknowledged own clear', records[scene['anomalies'][0]['id']]['receipt']['severity'] == 0)
            session.edit('clear', {'id': second['id']})
        finally:
            session.close()
        check('experiment removed after scoped cleanup', observer.get('/v1/experiments/'+epoch).status_code == 404)
        check('experiment count restored after own cleanup', observer.get('/health').json()['experiments'] == initial_count)
        # A second physical run exercises buffering without radio coverage.
        buffered = deepcopy(scene)
        buffered['vehicles'] = {'probe': buffered['vehicles']['probe']}
        tower = buffered['towers'].pop()
        args.playground_scene = buffered
        session = PlaygroundSession(args, emit)
        try:
            for _ in range(300):
                session.step()
                if session.detected:
                    break
            check('out-of-coverage perception buffered on vehicle', bool(session.detected) and bool(session.knowledge['probe']) and not session.network['incidents'])
            session.edit('tower', tower)
            session.step()
            check('buffered report accepted after coverage restored', bool(session.published) and bool(session.network['incidents']))
        finally:
            session.close()
        check('both physical test experiments cleaned', observer.get('/health').json()['experiments'] == initial_count)
        result['checks'] = checks
        target = ROOT/'evidence/playground/physical-verification.json'
        target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(f'PHYSICAL_PLAYGROUND_VERIFIED: {len(checks)} checks passed; {target}', flush=True)
        return result


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18767')
    parser.add_argument('--map-id', default='delhi_urban')
    options = parser.parse_args()
    verify(options.url, options.map_id)
