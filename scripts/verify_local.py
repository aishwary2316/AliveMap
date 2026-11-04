"""Headless real-SUMO smoke test; never connects to a remote MEC service."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def isolated_backend():
    keys = ('ALIVEMAP_API_KEY', 'ALIVEMAP_STATE_DB', 'ALIVEMAP_LEGACY_URL')
    saved = {key: os.environ.pop(key) for key in keys if key in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify(region, output):
    from fastapi.testclient import TestClient
    from mec.baseline import main
    from mec.playground_api import create_app
    from routing_core.maps import PackageMapProvider, read_json
    from routing_core.playground import story_scene
    from laptop.playground_session import PlaygroundSession

    directory = ROOT / 'map_packages' / region
    provider = PackageMapProvider(directory / read_json(directory/'active.json')['revision'])
    scenario = read_json(provider.path/provider.manifest['scenario'])
    incident = story_scene(provider, scenario, scenario['hazard']['kind'])
    baseline = story_scene(provider, scenario, 'none')
    require(incident['vehicles'] == baseline['vehicles'], 'Baseline trips differ from incident trips')
    baseline_http = TestClient(main.app)

    def bridge(payload):
        response = baseline_http.post('/hazards', json=payload)
        response.raise_for_status()
        return response.json()

    result = {'region': region, 'build_id': provider.manifest['build_id']}
    try:
        for kind, scene in (('incident', incident), ('baseline', baseline)):
            args = SimpleNamespace(gui=False, mec_mode='local', mec_url=None, semantics_url=None,
                playground_url=None, map_package=provider.path, output=str(output),
                playground_scene=scene, incident_kind='none')
            session = PlaygroundSession(args, http=TestClient(create_app(bridge)))
            try:
                if kind == 'incident':
                    for _ in range(1800):
                        session.step()
                        records = session.network.get('incidents', [])
                        if records and len(records[0].get('reporters', [])) >= 2:
                            break
                    require(bool(records), 'No incident reached the local MEC')
                    record = records[0]
                    require(set(record['reporters']) == {'scout-1', 'scout-2'}, 'Expected two independent scouts')
                    require(record['assessment']['confidence'] == 'corroborated', 'MEC did not corroborate reports')
                    require(bool(record['h3_cells']['10']), 'MEC returned no affected H3 cells')
                    acks = [e for e in session.radio_events if e.get('stage') == 'acknowledged']
                    times = [e['sim_time'] for e in acks]
                    require(len(set(times)) == 2, 'Scouts did not report at separate simulation times')
                    require(session.reroute_counts['cautious'] > 0 or 'cautious' in session.blocked,
                            'Affected receiver neither rerouted nor stopped for a blocked route')
                    for history in session.route_history.values():
                        for change in history:
                            if change['new']:
                                provider.validate_route(change['new'])
                    result.update(report_times_sim_seconds=times,
                        affected_receiver_reroutes=session.reroute_counts['cautious'],
                        affected_receiver_blocked='cautious' in session.blocked,
                        h3_micro_cells=len(record['h3_cells']['10']))
                else:
                    for _ in range(80):
                        session.step()
                    require(not session.network['incidents'], 'Baseline unexpectedly contains an incident')
                    require(not sum(session.reroute_counts.values()), 'Baseline unexpectedly rerouted')
                    result['same_trip_baseline_passed'] = True
            finally:
                session.close()
    finally:
        baseline_http.close()
    result['passed'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maps', nargs='+', default=['delhi_urban'],
        choices=tuple(json.loads((ROOT/'geospatial/definitions.json').read_text())))
    parser.add_argument('--output', type=Path, default=ROOT/'runs/setup-verification')
    args = parser.parse_args()
    with isolated_backend():
        results = [verify(region, args.output) for region in args.maps]
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'backend': 'local in-process API',
              'physical_mec_contacted': False, 'results': results}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
