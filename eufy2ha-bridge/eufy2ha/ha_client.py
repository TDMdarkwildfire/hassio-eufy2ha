"""Tiny Home Assistant REST client — just the service calls the concierge needs.

In the add-on: base_url=http://supervisor/core/api, token=$SUPERVISOR_TOKEN
(requires `homeassistant_api: true`). In dev: HA_URL + HA_TOKEN.
"""
from __future__ import annotations

import json
import urllib.request


class HaClient:
    def __init__(self, base_url: str, token: str):
        self._base = base_url.rstrip("/")
        self._token = token

    def call_service(self, domain: str, service: str, data: dict) -> bool:
        url = f"{self._base}/services/{domain}/{service}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return 200 <= r.status < 300
        except Exception:
            return False

    def stop_p2p(self, entity_id: str) -> bool:
        return self.call_service("eufy_security", "stop_p2p_livestream",
                                 {"entity_id": entity_id})

    def get_state(self, entity_id: str) -> str | None:
        url = f"{self._base}/states/{entity_id}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode()).get("state")
        except Exception:
            return None
