"""Additive read-only semantic view of the existing MEC /hazards API.

Runs separately; no duplicate hazard store, legacy-source edits or restart required.
"""
import hashlib
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query


def create_app(upstream=None, fetch=None):
    upstream = upstream or os.environ.get("ALIVEMAP_UPSTREAM", "http://127.0.0.1:8765")
    parsed = urlparse(upstream)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Upstream must be the local existing MEC API")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def default_fetch(path):
        with opener.open(upstream.rstrip("/") + path, timeout=5) as response:
            return json.load(response)

    fetch = fetch or default_fetch
    app = FastAPI(title="AliveMap semantic view", version="1")

    def read(path):
        try:
            return fetch(path)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            raise HTTPException(503, "Existing MEC API unavailable or malformed") from exc

    @app.get("/health")
    def health():
        body = read("/health")
        if not isinstance(body, dict) or body.get("service") != "mec-av-poc" or body.get("status") != "ok":
            raise HTTPException(503, "Upstream does not identify the inspected MEC API")
        return {"status": "ok", "service": "alivemap-semantic-view", "upstream_status": body.get("status")}

    @app.get("/semantics")
    def semantics(prefix: str = Query(min_length=1, max_length=256)):
        body = read("/hazards")
        if not isinstance(body, dict) or not isinstance(body.get("events"), list):
            raise HTTPException(503, "Unexpected upstream hazards schema")
        events = [event for event in body["events"]
                  if isinstance(event, dict) and str(event.get("event_id", "")).startswith(prefix)]
        fields = ("event_id", "vehicle_id", "latitude", "longitude", "event_type", "severity")
        try:
            semantic = [{key: event[key] for key in fields} for event in events]
            semantic.sort(key=lambda event: event["event_id"])
            content = json.dumps(semantic, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(503, "Malformed upstream event") from exc
        return {"schema_version": 1, "prefix": prefix,
                "revision": hashlib.sha256(content.encode()).hexdigest(), "events": events}

    return app
