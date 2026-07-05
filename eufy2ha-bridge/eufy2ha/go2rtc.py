"""Poll go2rtc for per-camera (has_live_producer, viewer_count).

A camera maps to one or more go2rtc stream names (the eufy serial stream and
the AlexxIT `camera.<x>` wrapper). A producer whose url is the AlexxIT
placeholder `tcp://127.0.0.1:65535` is NOT live; anything else means frames are
flowing. viewers = max consumers across the camera's streams.
"""
from __future__ import annotations

import json
import urllib.request

PLACEHOLDER = "127.0.0.1:65535"


class Go2rtc:
    def __init__(self, base_url: str):
        self._url = base_url.rstrip("/") + "/api/streams"

    def _fetch(self) -> dict:
        with urllib.request.urlopen(self._url, timeout=5) as r:
            return json.loads(r.read().decode())

    def states(self, cameras: dict[str, list[str]]) -> dict[str, tuple[bool, int]]:
        """cameras: cam_key -> [go2rtc stream names]. Returns cam -> (live, viewers)."""
        try:
            data = self._fetch()
        except Exception:
            return {}
        out: dict[str, tuple[bool, int]] = {}
        for cam, names in cameras.items():
            live = False
            viewers = 0
            for name in names:
                info = data.get(name)
                if not info:
                    continue
                producers = info.get("producers") or []
                if any(PLACEHOLDER not in (p.get("url", "")) for p in producers):
                    live = True
                consumers = info.get("consumers") or []
                viewers = max(viewers, len(consumers))
            out[cam] = (live, viewers)
        return out
