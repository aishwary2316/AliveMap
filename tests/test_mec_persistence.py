from uuid import uuid4

from fastapi.testclient import TestClient

from mec.playground_api import create_app


def test_database_survives_restart_preserves_versions_and_scoped_cleanup(tmp_path):
    # Reuse the reviewed baseline HTTP implementation rather than fabricate ACKs.
    from mec.baseline.main import app
    legacy=TestClient(app)
    def bridge(payload):
        response=legacy.post('/hazards',json=payload);response.raise_for_status();return response.json()
    path=tmp_path/'state.sqlite3'
    eid=str(uuid4());route='/v1/experiments/'+eid
    experiment={'experiment_id':eid,'map_id':'test','bounds':[77.2,28.6,77.3,28.7],
                'towers':[{'id':'tower','longitude':77.25,'latitude':28.63,'radius_m':1000}]}
    client=TestClient(create_app(bridge,state_path=path))
    client.post('/v1/experiments',json=experiment).raise_for_status()
    telemetry={'sim_time':2,'vehicles':[{'id':'car','longitude':77.25,'latitude':28.63,'role':'both'}]}
    client.post(route+'/tick',json=telemetry).raise_for_status()
    report={'incident_id':'hazard','vehicle_id':'car','longitude':77.25,'latitude':28.63,'kind':'landslide','event_version':1,
            'geometry':{'type':'Polygon','coordinates':[[[77.249,28.629],[77.251,28.629],[77.251,28.631],[77.249,28.631],[77.249,28.629]]]}}
    original=client.post(route+'/observations',json=report).json()['incident']
    client.app.state.database.close()
    restored=TestClient(create_app(bridge,state_path=path))
    snapshot=restored.get(route).json()
    assert snapshot['sim_time']==2 and snapshot['incidents'][0]==original
    assert snapshot['deliveries']['car'][0]['id']=='hazard'
    assert restored.post(route+'/observations',json=report).json()['deduplicated']
    restored.delete(route).raise_for_status()
    restored.app.state.database.close()
    fresh=TestClient(create_app(bridge,state_path=path))
    assert fresh.get(route).status_code==404
    assert fresh.get('/health').json()['state_storage']=='sqlite'
    fresh.app.state.database.close()


def test_remote_origin_requires_bearer_and_does_not_echo_secrets():
    secret='test-only-secret-'+'a'*32
    client=TestClient(create_app(api_key=secret))
    assert client.get('/health').status_code==401
    rejected=client.get('/health',headers={'Authorization':'Bearer wrong'})
    assert rejected.status_code==401 and secret not in rejected.text
    accepted=client.get('/health',headers={'Authorization':'Bearer '+secret})
    assert accepted.status_code==200 and accepted.json()['authentication']=='bearer'
    assert secret not in accepted.text


def test_guided_controller_compatibility_routes_are_authenticated_and_bounded():
    from mec.baseline.main import app
    secret='compatibility-test-'+'b'*32
    legacy=TestClient(app)
    service=TestClient(create_app(api_key=secret,legacy_http=legacy))
    assert service.get('/legacy/hazards').status_code==401
    headers={'Authorization':'Bearer '+secret}
    assert service.get('/legacy/health',headers=headers).json()['service']=='mec-av-poc'
    assert service.get('/legacy/openapi.json',headers=headers).json()==legacy.get('/openapi.json').json()
    payload={'event_id':'compatibility-test','vehicle_id':'probe','latitude':28.63,'longitude':77.25,'event_type':'test','severity':.5}
    response=service.post('/legacy/hazards',json=payload,headers=headers)
    assert response.status_code==200 and response.json()['accepted']
    assert service.post('/legacy/health',json={},headers=headers).status_code==405
    assert service.get('/legacy/arbitrary-service',headers=headers).status_code==404
