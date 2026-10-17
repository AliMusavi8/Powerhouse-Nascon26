import os

import pytest
import requests

BASE = os.environ.get("API_BASE", "http://localhost:8080")


class Client:
    def __init__(self, base: str):
        self.base = base
        self.s = requests.Session()

    def post(self, path, body=None, **kw):
        return self.s.post(self.base + path, json=body, timeout=15, **kw)

    def get(self, path, **kw):
        return self.s.get(self.base + path, timeout=15, **kw)

    def patch(self, path, body=None, **kw):
        return self.s.patch(self.base + path, json=body, timeout=15, **kw)

    def reset(self, **body):
        r = self.post("/audit/v1/reset", body or {})
        assert r.status_code == 200
        return r.json()


@pytest.fixture(scope="session")
def api():
    try:
        requests.get(BASE + "/health", timeout=3)
    except requests.RequestException:
        pytest.skip("API not running on " + BASE)
    return Client(BASE)


@pytest.fixture()
def fresh(api):
    api.reset()
    return api
