"""Typed MEC playground client, usable unchanged locally or through SSH."""
import httpx
from urllib.parse import urlparse

from mec.playground_api import SERVICE


class PlaygroundClient:
    def __init__(self, url, experiment, map_id, bounds, towers, http=None):
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Use the loopback endpoint of the MEC SSH forward")
        self.http = http or httpx.Client(base_url=url, timeout=8, trust_env=False)
        self.id, self.map_id, self.bounds, self.towers = experiment, map_id, bounds, towers
        self.path = "/v1/experiments/"+experiment
        self.registered, self.attempted_report = False, False

    def preflight(self, _schema=None):
        health = self.http.get("/health"); health.raise_for_status()
        if health.json().get("service") != SERVICE or health.json().get("schema_version") != 1 or health.json().get("delivery_revision") != 2:
            raise ValueError("Endpoint is not the reviewed MEC playground API")
        result = self.http.post("/v1/experiments", json={"experiment_id": self.id, "map_id": self.map_id, "bounds": self.bounds, "towers": self.towers})
        result.raise_for_status()
        self.registered = True

    def facts(self):
        response = self.http.get(self.path); response.raise_for_status()
        return response.json()

    def tick(self, sim_time, vehicles):
        response = self.http.post(self.path+"/tick", json={"sim_time": sim_time, "vehicles": vehicles})
        response.raise_for_status()
        return response.json()

    def set_towers(self, towers):
        response = self.http.put(self.path+"/towers", json=towers); response.raise_for_status()
        return response.json()

    def observe(self, payload):
        self.attempted_report = True
        response = self.http.post(self.path+"/observations", json=payload)
        if response.status_code == 409 and "NO_COVERAGE" in response.text:
            return None
        response.raise_for_status()
        return response.json()

    def close(self):
        try:
            if self.registered:
                response = self.http.delete(self.path)
                response.raise_for_status()
                self.registered = False
        finally:
            self.http.close()
