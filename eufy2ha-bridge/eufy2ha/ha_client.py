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
        st = self._get_entity(entity_id)
        return st.get("state") if st else None

    def get_entity_picture(self, entity_id: str) -> str | None:
        st = self._get_entity(entity_id)
        return (st.get("attributes", {}) or {}).get("entity_picture") if st else None

    def _get_entity(self, entity_id: str) -> dict | None:
        url = f"{self._base}/states/{entity_id}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode())
        except Exception:
            return None

    def notify(self, service_full: str, title: str, message: str, data: dict | None = None) -> bool:
        # service_full e.g. "notify.mobile_app_iphone_philip"
        domain, _, service = service_full.partition(".")
        payload = {"title": title, "message": message}
        if data:
            payload["data"] = data
        return self.call_service(domain or "notify", service, payload)
