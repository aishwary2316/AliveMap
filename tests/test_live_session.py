from types import SimpleNamespace

from fastapi.testclient import TestClient

from laptop.live_session import LiveSession
from mec.baseline import main


def test_visible_session_engine_steps_and_applies_manual_mec_updates(tmp_path):
    main.events.clear()
    args = SimpleNamespace(gui=False, mec_url="http://127.0.0.1", semantics_url=None, output=str(tmp_path))
    with TestClient(main.app) as client:
        session = LiveSession(args, http=client)
        try:
            initial = session.frame()
            assert initial["time"] == 0.5
            assert set(initial["vehicles"]) == {"cautious", "standard", "unaffected", "probe"}
            assert not main.events  # Starting the lab does not invent a remote hazard.
            session.report("warning")
            warning = session.frame()
            assert warning["time"] == 0.5  # Reporting while paused does not advance SUMO.
            assert session.hazard_edge not in warning["vehicles"]["cautious"]["route"]
            assert session.hazard_edge in warning["vehicles"]["standard"]["route"]
            session.report("closed")
            closed = session.frame()
            assert all(session.hazard_edge not in closed["vehicles"][v]["route"] for v in ("cautious", "standard"))
            session.step()
            assert session.frame()["time"] == 1.0
            session.report("clear")
            cleared = session.frame()
            assert cleared["state"] == "clear" and "probe" not in cleared["vehicles"]
        finally:
            session.close()


def test_closing_manual_session_clears_only_its_own_event(tmp_path):
    main.events.clear()
    args = SimpleNamespace(gui=False, mec_url="http://127.0.0.1", semantics_url=None, output=str(tmp_path))
    with TestClient(main.app) as client:
        original = dict(event_id="keep-me", vehicle_id="existing", latitude=0, longitude=0,
                        event_type="existing", severity=0.2)
        saved = client.post("/hazards", json=original).json()["event"]
        session = LiveSession(args, http=client)
        session.report("closed")
        event_id = session.client.prefix + "demo-road"
        session.close()
        assert main.events[event_id]["event_type"] == "alivemap.clear"
        assert main.events["keep-me"] == saved
