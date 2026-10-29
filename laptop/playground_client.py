"""Typed MEC playground client, usable unchanged locally or through SSH."""
import httpx
import time
from .endpoint import endpoint

from mec.playground_api import SERVICE


class PlaygroundClient:
    def __init__(self, url, experiment, map_id, bounds, towers, http=None):
        if http is None:
            url, headers = endpoint(url)
            self.endpoint_url = url
            self.http = httpx.Client(base_url=url, headers=headers, timeout=10, trust_env=False,
                                     verify=True, follow_redirects=False)
        else:
            self.http = http
            self.endpoint_url = 'local demo backend'
        self.id, self.map_id, self.bounds, self.towers = experiment, map_id, bounds, towers
        self.path = "/v1/experiments/"+experiment
        self.registered, self.attempted_report = False, False

    def request(self, method, path, **kwargs):
        """Bounded retries for reads and operations with explicit idempotency.

        Registration and deletion deliberately use their single-request paths.
        Incident versions, full tower replacement and equal-time telemetry are
        idempotent on MEC. Authentication/validation/coverage failures are final.
        """
        for attempt in range(5):
            try:
                response = self.http.request(method, path, **kwargs)
                if response.status_code >= 500:
                    response.raise_for_status()
                return response
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == 4:
                    raise
                time.sleep(min(.5*2**attempt, 2))

    def preflight(self, _schema=None):
        health = self.request('GET', "/health"); health.raise_for_status()
        if health.json().get("service") != SERVICE or health.json().get("schema_version") != 1 or health.json().get("delivery_revision") != 2:
            raise ValueError("Endpoint is not the reviewed MEC playground API")
        result = self.http.post("/v1/experiments", json={"experiment_id": self.id, "map_id": self.map_id, "bounds": self.bounds, "towers": self.towers})
        result.raise_for_status()
        self.registered = True

    def facts(self):
        response = self.request('GET', self.path); response.raise_for_status()
        return response.json()

    def tick(self, sim_time, vehicles):
        response = self.request('POST', self.path+"/tick", json={"sim_time": sim_time, "vehicles": vehicles})
        response.raise_for_status()
        return response.json()

    def set_towers(self, towers):
        response = self.request('PUT', self.path+"/towers", json=towers); response.raise_for_status()
        return response.json()

    def observe(self, payload):
        self.attempted_report = True
        response = self.request('POST', self.path+"/observations", json=payload)
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
