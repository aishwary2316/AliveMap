"""Versioned geographic facts over the existing, unchanged MEC contract.

The legacy server validates/stamps/indexes the outer record. This bridge validates
the structured event_type envelope and enforces expiry and experiment scope.
"""
import json
from dataclasses import asdict
from datetime import datetime, timezone

from shapely.geometry import shape

from routing_core.agents import Observation
from .mec_client import MecClient, revision

TAG = "alivemap.geo.v1:"


class GeoMecClient(MecClient):
    def report_fact(self, fact):
        fact.validate()
        if fact.experiment_id != self.experiment_id or fact.map_id != self.map_id:
            raise ValueError("Cannot publish another experiment's fact")
        point = shape(fact.geometry).centroid
        payload = dict(event_id=self.prefix+"area", vehicle_id="scenario-observer",
                       latitude=point.y, longitude=point.x,
                       event_type=TAG+json.dumps(asdict(fact), sort_keys=True, separators=(",", ":")),
                       severity=0.0 if fact.kind == "clear" else 0.7)
        return self.post_payload(payload)

    def __init__(self, url, experiment_id, map_id, **kwargs):
        super().__init__(url, experiment_id, map_id, **kwargs)
        self.experiment_id, self.map_id = experiment_id, map_id
        self.versions = {}

    def facts(self, now=None):
        if self.semantics_url:
            body = self.get(self.semantics_url, params={"prefix": self.prefix}).json()
            raw = body["events"]
            if body.get("schema_version") != 1 or body.get("prefix") != self.prefix or body.get("revision") != revision(raw):
                raise ValueError("Invalid semantic view response")
        else:
            raw = self.all_events()
        records = [self.validate(event) for event in raw if isinstance(event, dict) and str(event.get("event_id", "")).startswith(self.prefix)]
        ids = [event["event_id"] for event in records]
        if len(ids) != len(set(ids)) or not self.acknowledged_ids.issubset(ids):
            raise RuntimeError("Acknowledged MEC state disappeared or duplicated; pause and reconnect")
        facts, active_records = [], []
        for event in records:
            if not event["event_type"].startswith(TAG):
                raise ValueError("Invalid geographic fact envelope")
            fact = Observation(**json.loads(event["event_type"][len(TAG):])).validate()
            if fact.experiment_id != self.experiment_id or fact.map_id != self.map_id:
                raise ValueError("MEC event scope disagrees with its ID")
            previous = self.versions.get(event["event_id"])
            signature = event["event_type"]
            if previous and (fact.event_version < previous[0] or (fact.event_version == previous[0] and signature != previous[1])):
                raise ValueError("Stale or conflicting event version")
            self.versions[event["event_id"]] = (fact.event_version, signature)
            if fact.active(now or datetime.now(timezone.utc)):
                facts.append(fact)
                active_records.append(event)
        current = revision(active_records)
        if current != self.last_revision:
            self.change_number += 1
            self.last_revision = current
        return {"version": self.change_number, "revision": current, "facts": facts, "records": records}
