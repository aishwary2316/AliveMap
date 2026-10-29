"""Real SUMO + local MEC stories, independent scouts and operator workflows."""
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from routing_core.maps import PackageMapProvider,read_json
from routing_core.playground import story_scene
from laptop.playground_session import PlaygroundSession
from test_geo_maps import package
from test_playground import backend


@pytest.mark.parametrize('name',['delhi_urban','gujarat_coastal','manipur_mantripukhri','manipur_mayangkhang'])
def test_two_independent_reporters_and_identical_clear_baseline(name,tmp_path):
    provider=PackageMapProvider(package(name))
    scenario=read_json(provider.path/provider.manifest['scenario'])
    scene=story_scene(provider,scenario,scenario['hazard']['kind'])
    baseline=story_scene(provider,scenario,'none')
    assert scene['vehicles']==baseline['vehicles']
    args=SimpleNamespace(gui=False,mec_mode='local',mec_url=None,semantics_url=None,playground_url=None,
        map_package=provider.path,output=tmp_path,playground_scene=scene,incident_kind='none')
    session=PlaygroundSession(args,http=TestClient(backend()))
    try:
        for _ in range(1800):
            session.step()
            if session.network['incidents'] and len(session.network['incidents'][0].get('reporters',[]))>=2:break
        assert len(session.network['incidents'])==1
        incident=session.network['incidents'][0]
        assert set(incident['reporters'])=={'scout-1','scout-2'}
        assert incident['assessment']['confidence']=='corroborated'
        assert incident['assessment']['severity']>0 and incident['h3_cells']['10']
        acks=[e for e in session.radio_events if e.get('stage')=='acknowledged']
        assert {e['vehicle'] for e in acks}=={'scout-1','scout-2'}
        assert len({e['sim_time'] for e in acks})==2,'scouts did not discover separately'
        assert session.knowledge.get('cautious')
        assert session.reroute_counts['cautious']>0 or 'cautious' in session.blocked
        assert session.route_history['cautious']
        for record in session.route_history['cautious']:
            if record['new']:provider.validate_route(record['new'])
        # Retransmission by an acknowledged reporter cannot inflate corroboration.
        # Perception itself must not repeatedly upload on later steps.
        for _ in range(4):session.step()
        assert len([e for e in session.radio_events if e.get('stage')=='acknowledged'])==2
        print(name,{'reported_at':[e['sim_time'] for e in acks],'reroutes':session.reroute_counts},flush=True)
    finally:session.close()
    args.playground_scene=baseline
    session=PlaygroundSession(args,http=TestClient(backend()))
    try:
        for _ in range(80):session.step()
        assert not session.network['incidents'] and not session.detected
        assert sum(session.reroute_counts.values())==0
    finally:session.close()


def test_failed_remote_cleanup_does_not_prevent_loading_local(tmp_path):
    import time
    from laptop.lab import LabWorker
    class OldUnavailable:
        def close(self):raise OSError('MEC unavailable during old experiment cleanup')
    args=SimpleNamespace(gui=False,defer_start=True,map_package=None,scenario=None,mec_mode='local',
        mec_url=None,semantics_url=None,playground_url=None,output=str(tmp_path))
    worker=LabWorker(args);worker.session=OldUnavailable();worker.start()
    try:
        worker.commands.put(('prepare_scene',(str(package()),True,{'mec_mode':'local','story_kind':'none','autoplay':False})))
        deadline=time.monotonic()+30;events=[]
        while time.monotonic()<deadline:
            event=worker.updates.get(timeout=10);events.append(event)
            assert event['kind']!='error',event
            if event['kind']=='frame':
                assert event['healthy'] and event['mec_mode']=='local' and event['playground']
                break
        else:raise AssertionError('No local scene after cleanup failure')
        assert any(e['kind']=='cleanup_error' for e in events)
    finally:
        worker.commands.put(('stop',None));worker.join(timeout=15)
        assert not worker.is_alive()


def test_existing_vehicle_can_be_explicitly_relocated_and_continue(tmp_path):
    from routing_core.playground import empty_scene
    provider=PackageMapProvider(package())
    args=SimpleNamespace(gui=False,mec_mode='local',mec_url=None,semantics_url=None,playground_url=None,
        map_package=provider.path,output=tmp_path,playground_scene=empty_scene(provider),incident_kind='none')
    session=PlaygroundSession(args,http=TestClient(backend()))
    try:
        scenario=read_json(provider.path/provider.manifest['scenario'])
        vehicle={**scenario['vehicles']['cautious'],'role':'both'}
        session.edit('vehicle',{'id':'custom',**vehicle})
        for _ in range(4):session.step()
        assert 'custom' in session.frame()['vehicles']
        route=session.baseline['custom'];origin=next(eid for eid in route[3:] if provider.edges[eid]['sumo_length_m']>40)
        session.edit('vehicle',{'id':'custom',**vehicle,'origin':origin,'position_m':5,'role':'receiver'})
        assert session.frame()['vehicle_status']['custom']=='queued'
        session.step()
        state=session.adapter.vehicle_state('custom')
        assert state['edge']==origin and session.fleet['custom']['role']=='receiver'
        assert any(e.get('stage')=='manual_placement' for e in session.radio_events)
        previous=state['position']
        for _ in range(5):session.step()
        assert session.adapter.vehicle_state('custom')['position']!=previous
    finally:session.close()
