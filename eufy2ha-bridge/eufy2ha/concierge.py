"""Live-view concierge — pure state logic.

Observation (verified on this setup): opening a camera card makes go2rtc report
a real producer + consumers>0; CLOSING the card leaves the P2P producer running
with consumers==0 (the battery drain). The concierge watches per-camera
(has_producer, viewers) and, when a camera has a live producer but zero viewers
for `grace_seconds`, emits a STOP so the bridge tears the P2P down.

Start is automatic (go2rtc on-demand), so the concierge only ever *stops*.
Switching A->B is handled for free: opening B drops A's viewers to 0, so A is
stopped after the grace period.
"""
from __future__ import annotations


class Concierge:
    def __init__(self, grace_seconds: float = 10.0):
        self.grace = grace_seconds
        self._zero_since: dict[str, float] = {}   # cam -> ts viewers hit 0

    def evaluate(self, states: dict[str, tuple[bool, int]], now: float) -> list[str]:
        """states: cam -> (has_live_producer, viewer_count). Returns cams to stop.

        On a grace crossing we emit a stop and re-arm the timer to `now`, so a
        stream that keeps lingering (stop failed / go2rtc lag) is retried every
        grace period rather than abandoned. A successful stop flips the producer
        to idle, which clears the timer and ends the retries.
        """
        to_stop: list[str] = []
        for cam, (live, viewers) in states.items():
            if viewers > 0 or not live:
                # watched, or nothing running -> clear timer
                self._zero_since.pop(cam, None)
                continue
            # live producer, no viewers -> candidate for stop
            start = self._zero_since.get(cam)
            if start is None:
                self._zero_since[cam] = now
            elif now - start >= self.grace:
                to_stop.append(cam)
                self._zero_since[cam] = now   # re-arm for retry
        return to_stop
