"""Isolated, durable POC semantic API. Does not import or modify the old API."""
import hmac
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

import h3
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    hazard_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    revision: int = Field(ge=1)
    network_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    reporter: str = Field(min_length=1, max_length=64)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    state: Literal["warning", "closed", "clear"]
    ttl_seconds: int = Field(default=600, ge=10, le=3600)


def create_app(db_path=None, token=None, now=time.time):
    token = token or os.environ.get("POC_TOKEN")
    if not token or len(token) < 16:
        raise RuntimeError("Set POC_TOKEN to a random secret of at least 16 characters")
    path = Path(db_path or os.environ.get("POC_DB", "data/poc.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect():
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS runs(run TEXT PRIMARY KEY, version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS hazards(
          run TEXT, id TEXT, revision INTEGER, payload TEXT, expires REAL, expired INTEGER,
          PRIMARY KEY(run,id));
        """)

    def auth(x_poc_token: str = Header(default="")):
        if not hmac.compare_digest(x_poc_token, token):
            raise HTTPException(401, "Invalid POC token")

    def expire(db, run):
        count = db.execute(
            "UPDATE hazards SET expired=1 WHERE run=? AND expired=0 AND expires<=?",
            (run, now()),
        ).rowcount
        if count:
            db.execute("UPDATE runs SET version=version+1 WHERE run=?", (run,))

    app = FastAPI(title="MEC routing POC sidecar", version="1")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "mec-routing-poc", "schema": 1}

    @app.post("/v1/runs/{run}/hazards", dependencies=[Depends(auth)])
    def report(run: UUID, item: Report):
        run = str(run)
        payload = json.dumps(item.model_dump(), sort_keys=True)
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO runs VALUES (?,0)", (run,))
            expire(db, run)
            old = db.execute("SELECT * FROM hazards WHERE run=? AND id=?", (run, item.hazard_id)).fetchone()
            if old and item.revision <= old["revision"]:
                if item.revision != old["revision"] or payload != old["payload"]:
                    raise HTTPException(409, "Revision stale or conflicts with accepted report")
                # Retry of exactly the same request is idempotent; it does not renew TTL.
            else:
                db.execute("INSERT OR REPLACE INTO hazards VALUES (?,?,?,?,?,0)",
                           (run, item.hazard_id, item.revision, payload, now() + item.ttl_seconds))
                db.execute("UPDATE runs SET version=version+1 WHERE run=?", (run,))
            version = db.execute("SELECT version FROM runs WHERE run=?", (run,)).fetchone()[0]
        return {"version": version, "h3_cell": h3.latlng_to_cell(item.lat, item.lon, 12)}

    @app.get("/v1/runs/{run}/semantics", dependencies=[Depends(auth)])
    def semantics(run: UUID):
        run = str(run)
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            expire(db, run)
            row = db.execute("SELECT version FROM runs WHERE run=?", (run,)).fetchone()
            result = []
            for row_h in db.execute("SELECT * FROM hazards WHERE run=? AND expired=0 ORDER BY id", (run,)):
                item = json.loads(row_h["payload"])
                if item["state"] != "clear":
                    result.append({**item, "expires_at": row_h["expires"],
                                   "h3_cell": h3.latlng_to_cell(item["lat"], item["lon"], 12)})
        return {"schema": 1, "run_id": run, "version": row[0] if row else 0, "hazards": result}

    return app
