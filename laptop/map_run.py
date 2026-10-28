"""Reproducible real-map experiment; uses the same session as the desktop UI."""
import argparse
import json
import time
from pathlib import Path

from .geo_session import GeoSession
from .map_launcher import available_packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", choices=list(available_packages()))
    parser.add_argument("--mec-url", default="http://127.0.0.1:18765")
    parser.add_argument("--semantics-url", default=None)
    parser.add_argument("--output", default="runs/maps")
    parser.add_argument("--scenario", default=None, help="Separate validated scenario JSON for this exact map/build")
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--delay", type=float, default=0)
    parser.add_argument("--max-time", type=float, default=1800)
    parser.add_argument("--incident-only", action="store_true", help="Keep primary incident active to measure profile-dependent driven paths")
    args = parser.parse_args()
    args.map_package = available_packages()[args.package]
    events = []
    session = GeoSession(args, lambda kind, **data: events.append({"event": kind, **data}))
    phase, driven, screenshot = 0, {name: [] for name in session.fleet}, False
    last_poll = time.monotonic()
    try:
        timeline = session.scenario["events"][:1] if args.incident_only else session.scenario["events"]
        while not session.complete and session.sim_time < args.max_time:
            frame = session.frame()
            for name, state in frame["vehicles"].items():
                if not driven[name] or driven[name][-1] != state["edge"]:
                    driven[name].append(state["edge"])
            if phase < len(timeline) and session.sim_time >= timeline[phase]["sim_time_s"]:
                session.report(timeline[phase]["kind"])
                phase += 1
            if args.gui and session.sim_time >= 10 and not screenshot:
                session.connection.gui.screenshot("View #0", str((session.output/"simulation.png").resolve()), 1400, 900)
                screenshot = True
            session.step()
            if time.monotonic()-last_poll >= 1:
                session.refresh()
                last_poll = time.monotonic()
            if args.delay:
                time.sleep(args.delay)
        summary = {"experiment_id": session.run_id, "map_id": session.network_id,
                   "build_id": session.provider.manifest["build_id"], "scenario_id": session.scenario["scenario_id"],
                   "transport": "HTTP polling via configured loopback endpoint; does not establish 5G bearer evidence",
                   "complete": session.complete, "arrived": sorted(session.arrived), "sim_time_s": session.sim_time,
                   "baseline": session.baseline, "driven_edges": driven,
                   "affected_edges": session.scenario["validation"]["affected_edges"],
                   "report_count": sum(e["event"] == "report" for e in events),
                   "changed_decisions": sum(e["event"] == "decision" and e.get("after") != e.get("before") for e in events)}
        (session.output/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps({key: summary[key] for key in ("experiment_id", "map_id", "complete", "arrived", "sim_time_s", "report_count", "changed_decisions")}, indent=2))
        print("Evidence:", session.output)
        if not session.complete:
            raise RuntimeError("Run did not finish before the configured limit; inspect stopped vehicles/no-route evidence")
    finally:
        session.close()


if __name__ == "__main__":
    main()
