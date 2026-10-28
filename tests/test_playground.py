from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import h3
import pytest
from fastapi.testclient import TestClient

from mec.baseline import main
from mec.playground_api import create_app
from routing_core.maps import PackageMapProvider, read_json
from routing_core.playground import empty_scene, example_scene, validate_scene, road_placement
from laptop.playground_session import PlaygroundSession
from laptop.playground_editor import drawn_geometry
from laptop.route_drawing import retired_runs
from test_geo_maps import package


def backend():
    legacy = TestClient(main.app)
    def bridge(payload):
        response = legacy.post('/hazards', json=payload)
        response.raise_for_status()
        return response.json()
    return create_app(bridge)


def test_mec_multiple_incidents_roles_coverage_versions_clear_and_scope():
    main.events.clear()
    client = TestClient(backend())
    eid = str(uuid4()); path = '/v1/experiments/'+eid
    tower = {'id': 'gNB', 'longitude': 77.25, 'latitude': 28.63, 'radius_m': 1000}
    assert client.post('/v1/experiments', json={'experiment_id': eid, 'map_id': 'test', 'bounds': [77.2,28.6,77.3,28.7], 'towers': [tower]}).status_code == 200
    def telemetry(role, lon=77.25):
        return {'id': role, 'longitude': lon, 'latitude': 28.63, 'role': role}
    vehicles = [telemetry('both'), telemetry('receiver'), telemetry('reporter'), telemetry('offline')]
    client.post(path+'/tick', json={'sim_time': 1, 'vehicles': vehicles}).raise_for_status()
    geometry = {'type': 'Polygon', 'coordinates': [[[77.2498,28.6298],[77.2502,28.6298],[77.2502,28.6302],[77.2498,28.6302],[77.2498,28.6298]]]}
    report = {'incident_id':'a', 'vehicle_id':'both', 'longitude':77.25, 'latitude':28.63, 'kind':'flood', 'geometry':geometry,
              'facts':{'water_depth_m':.3}, 'event_version':1}
    result = client.post(path+'/observations', json=report)
    result.raise_for_status(); data = result.json()
    assert data['accepted'] and data['incident']['receipt']['h3_cell'] == h3.latlng_to_cell(28.63,77.25,10)
    assert data['incident']['h3_cells']['8'] and data['incident']['h3_cells']['10']
    assert len(data['network']['deliveries']['receiver']) == 1
    assert data['network']['deliveries']['offline'] == data['network']['deliveries']['reporter'] == []
    assert client.post(path+'/observations', json=report).json()['deduplicated']
    conflicting = {**report,'facts':{'water_depth_m':.4}}
    assert client.post(path+'/observations', json=conflicting).status_code == 409
    assert client.post(path+'/observations', json={**report,'vehicle_id':'receiver'}).status_code == 422
    client.post(path+'/observations', json={**report,'incident_id':'b'}).raise_for_status()
    cleared = client.post(path+'/observations', json={**report,'kind':'clear','event_version':2}).json()
    assert [r['status'] for r in cleared['network']['incidents']] == ['cleared','active']
    # Out of coverage cannot upload or receive; returning delivers current state.
    moved = [{**v, 'longitude':77.29} for v in vehicles]
    response = client.post(path+'/tick',json={'sim_time':2,'vehicles':moved}).json()
    assert all(not records for records in response['deliveries'].values())
    assert client.post(path+'/observations',json={**report,'incident_id':'c','longitude':77.29}).status_code == 409
    assert client.post(path+'/tick',json={'sim_time':3,'vehicles':vehicles}).json()['deliveries']['receiver'][0]['status'] == 'cleared'
    # Wall-time expiry is authoritative, and stale tick cannot rewind the world.
    client.app.state.experiments[eid]['incidents']['b']['observation']['expires_at'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    assert client.get(path).json()['incidents'][1]['status'] == 'expired'
    assert client.post(path+'/tick',json={'sim_time':1,'vehicles':vehicles}).status_code == 409
    # A second serving tower is selected by proximity; unrelated tower coverage
    # does not distribute the first tower's local incident.
    second={**tower,'id':'gNB-far','longitude':77.29,'radius_m':200}
    client.put(path+'/towers',json=[tower,second]).raise_for_status()
    newcomer={'id':'newcomer','longitude':77.29,'latitude':28.63,'role':'receiver'}
    handover=client.post(path+'/tick',json={'sim_time':4,'vehicles':moved+[newcomer]}).json()
    assert handover['associations']['both']['tower_id']=='gNB-far'
    assert not handover['deliveries']['newcomer']
    assert handover['deliveries']['receiver'][0]['status']=='cleared'
    returned=client.post(path+'/tick',json={'sim_time':5,'vehicles':vehicles}).json()
    assert returned['associations']['both']['tower_id']=='gNB' and returned['deliveries']['receiver']
    legacy = TestClient(main.app)
    legacy.post('/hazards',json={'event_id':'unrelated','vehicle_id':'other','latitude':28.63,'longitude':77.25,'event_type':'pothole','severity':.5})
    assert client.delete(path).json()['closed']
    assert main.events['unrelated']['event_type'] == 'pothole'
    assert client.get(path).status_code == 404


def test_mec_invalid_geometry_and_unacknowledged_bridge_never_publish():
    app = create_app(lambda _: {'accepted':False})
    client = TestClient(app); eid=str(uuid4()); path='/v1/experiments/'+eid
    client.post('/v1/experiments',json={'experiment_id':eid,'map_id':'test','bounds':[77.2,28.6,77.3,28.7],'towers':[]}).raise_for_status()
    report={'incident_id':'a','vehicle_id':'operator','longitude':77.25,'latitude':28.63,'kind':'landslide','event_version':1,
            'source_type':'synthetic_scenario','geometry':{'type':'Polygon','coordinates':[[[77.24,28.62],[77.26,28.64],[77.24,28.64],[77.26,28.62],[77.24,28.62]]]}}
    assert client.post(path+'/observations',json=report).status_code == 422
    report['geometry']['coordinates']=[[[77.249,28.629],[77.251,28.629],[77.251,28.631],[77.249,28.631],[77.249,28.629]]]
    assert client.post(path+'/observations',json=report).status_code == 502
    assert client.get(path).json()['incidents'] == []


@pytest.fixture(scope='module')
def provider():
    return PackageMapProvider(package())


def session_for(provider, scene, tmp_path):
    args=SimpleNamespace(gui=False,mec_url='http://127.0.0.1',semantics_url=None,playground_url='http://127.0.0.1',
                         map_package=provider.path,output=tmp_path,playground_scene=scene,incident_kind='none')
    return PlaygroundSession(args,http=TestClient(backend()))


def test_real_sumo_perception_mec_h3_individual_delivery_and_driven_detour(provider,tmp_path):
    main.events.clear()
    scene=example_scene(provider,read_json(provider.path/provider.manifest['scenario']))
    scene['vehicles']['standard']['role']='offline'
    session=session_for(provider,scene,tmp_path)
    try:
        assert not session.network['incidents']
        for _ in range(500):
            session.step()
            if session.network['incidents']:
                break
        assert session.network['incidents'], session.frame()
        record=session.network['incidents'][0]
        assert record['reporter'] != 'operator' and record['observation']['source_type']=='simulated_perception'
        assert record['receipt']['h3_cell'] and record['h3_cells']['10']
        assert session.detected and any(e.get('stage')=='acknowledged' for e in session.radio_events)
        assert session.knowledge['cautious'] and not session.knowledge['standard']
        assert session.reroute_counts['cautious'] >= 1
        assert session.reroute_counts['standard'] == 0
        affected=set(session.mapping[0]['edges'])
        assert not affected.intersection(session.frame()['vehicles']['cautious']['route'])
        for _ in range(2600):
            session.step()
            if 'cautious' in session.arrived:
                break
        assert 'cautious' in session.arrived
        assert not affected.intersection(session.driven_edges['cautious'])
        assert session.route_history['cautious']
    finally:
        session.close()


def test_empty_world_dynamic_edits_shapes_roles_save_and_multiple_clear(provider,tmp_path):
    scene=empty_scene(provider); session=session_for(provider,scene,tmp_path)
    try:
        session.step(); assert not session.complete
        sample=example_scene(provider,read_json(provider.path/provider.manifest['scenario']))
        v=sample['vehicles']['cautious']
        session.edit('vehicle',{'id':'custom',**v})
        for _ in range(5): session.step()
        assert 'custom' in session.frame()['vehicles']
        session.edit('vehicle',{'id':'custom',**v,'role':'receiver'})
        assert session.fleet['custom']['role']=='receiver'
        session.edit('tower',sample['towers'][0])
        a=sample['anomalies'][0]
        session.edit('anomaly',a); session.edit('anomaly',{**a,'id':'second'})
        assert not session.network['incidents']
        session.edit('publish',{'id':a['id']}); session.edit('publish',{'id':'second'})
        session.edit('clear',{'id':a['id']})
        assert [r['status'] for r in session.network['incidents']]==['cleared','active']
        assert 'second' in session.knowledge['custom'] and a['id'] not in session.knowledge['custom']
        exported=session.export_scene(); validate_scene(provider,exported)
        assert not any('disabled' in a for a in exported['anomalies'])
        session.edit('remove_anomaly',{'id':'second'})
        session.edit('remove_vehicle',{'id':'custom'})
        assert not session.fleet
        session.edit('remove_tower',{'id':sample['towers'][0]['id']})
        assert not session.network['towers']
    finally: session.close()
    edge=provider.edges[v['origin']]
    point=edge['shape_wgs84'][0]
    assert road_placement(provider,point)['edge'] in provider.edges
    for tool,points in [('circle',[point]),('rectangle',[point,[point[0]+.0001,point[1]+.0001]]),('polygon',[point,[point[0]+.0001,point[1]],[point[0],point[1]+.0001]])]:
        assert drawn_geometry(provider,tool,points)['type']=='Polygon'
    with pytest.raises(ValueError):
        validate_scene(provider,{**scene,'map_build_id':'wrong'})
    assert retired_runs(['a','b','c','d','e'],['a','x','c','y','e'])==[['b'],['d']]
    assert retired_runs(['a','b','c'],['a','b','c'])==[]


@pytest.mark.parametrize('map_id',['gujarat_coastal','manipur_mantripukhri','manipur_mayangkhang'])
def test_other_real_maps_support_perception_playground(map_id,tmp_path):
    provider=PackageMapProvider(package(map_id))
    scene=example_scene(provider,read_json(provider.path/provider.manifest['scenario']))
    session=session_for(provider,scene,tmp_path)
    try:
        for _ in range(1200):
            session.step()
            if session.network['incidents']:
                break
        assert session.network['incidents'], map_id
        record=session.network['incidents'][0]
        assert record['reporter']!='operator' and record['h3_cells']['8'] and record['h3_cells']['10']
        assert any(session.knowledge.values())
        assert any(session.reroute_counts.values()) or session.blocked, session.frame()
    finally: session.close()


def test_reporter_buffers_without_coverage_then_uploads_after_tower_added(provider,tmp_path):
    scene=example_scene(provider,read_json(provider.path/provider.manifest['scenario']))
    scene['vehicles']={'probe':scene['vehicles']['probe']}
    tower=scene['towers'].pop()
    session=session_for(provider,scene,tmp_path)
    try:
        for _ in range(300):
            session.step()
            if session.detected:
                break
        assert session.detected and session.knowledge['probe']
        assert not session.network['incidents'] and not session.published
        session.edit('tower',tower)
        session.step()
        assert session.published and session.network['incidents'][0]['reporter']=='probe'
    finally: session.close()
