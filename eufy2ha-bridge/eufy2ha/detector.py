"""Pure motion-detection logic for the polling bridge.

Eufy push is broken upstream (client issue #933, eufy_mega migration), so we
detect motion by POLLING `station.database_query_latest_info`, which returns a
per-device `event_count` and the newest event's crop (thumbnail) path. A rising
event_count means the camera recorded a new event. This module is the pure,
unit-tested core; all I/O lives in the bridge.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotionEvent:
    device_sn: str
    count: int
    delta: int
    crop_path: str


class MotionDetector:
    """Tracks per-device event_count and emits MotionEvents on increase.

    The first snapshot for a device only seeds the baseline (no event), so a
    restart doesn't replay the whole history as a fresh motion burst.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def seed(self, device_sn: str, count: int) -> None:
        """Establish a baseline without emitting (e.g. from startup state)."""
        self._counts[device_sn] = count

    def update(self, snapshot: list[dict]) -> list[MotionEvent]:
        """Feed one `database query latest` data list; return new events.

        Each item is expected to have `device_sn`, `event_count`, and one of
        `crop_local_path` / `crop_cloud_path`.
        """
        events: list[MotionEvent] = []
        for item in snapshot:
            sn = item.get("device_sn")
            if sn is None:
                continue
            count = item.get("event_count")
            if not isinstance(count, int):
                continue
            crop = item.get("crop_local_path") or item.get("crop_cloud_path") or ""
            prev = self._counts.get(sn)
            self._counts[sn] = count
            if prev is None:
                # first sighting -> baseline only
                continue
            if count > prev:
                events.append(
                    MotionEvent(device_sn=sn, count=count,
                                delta=count - prev, crop_path=crop)
                )
        return events
