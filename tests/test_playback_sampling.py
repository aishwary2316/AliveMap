from types import SimpleNamespace

from laptop.playground_session import PlaygroundSession


def test_sampling_triggers_coverage_handover_but_offline_role_does_not_force_network_waits():
    positions={'online':(77.25,28.63),'offline':(77.25,28.63)}
    session=object.__new__(PlaygroundSession)
    session.connection=SimpleNamespace(vehicle=SimpleNamespace(getIDList=lambda:list(positions)))
    session.fleet={'online':{'role':'both'},'offline':{'role':'offline'}}
    session.scene={'towers':[{'id':'tower','longitude':77.25,'latitude':28.63,'radius_m':100}]}
    session.adapter=SimpleNamespace(vehicle_state=lambda name:{'lonlat':positions[name]})
    session.network={'associations':{'online':{'tower_id':'tower'},'offline':{'tower_id':None}}}
    assert not session.radio_boundary_crossed()
    positions['online']=(77.26,28.63)
    assert session.radio_boundary_crossed()
    session.network['associations']['online']['tower_id']=None
    assert not session.radio_boundary_crossed()
    positions['online']=(77.25,28.63)
    assert session.radio_boundary_crossed()
