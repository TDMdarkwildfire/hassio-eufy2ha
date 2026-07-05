"""eufy2ha polling bridge — main service.

Replaces the (upstream-broken) Eufy push path with polling:
  poll station.database_query_latest_info -> detect event_count rise ->
  download the event thumbnail -> publish motion + thumbnail + event to HA
  over MQTT discovery.

Run: python -m eufy2ha.bridge  (config from env / config.json)
"""
from __future__ import annotations

import datetime
import json
import os
import socket
import sys
import time

from .concierge import Concierge
from .detector import MotionDetector
from .go2rtc import Go2rtc
from .ha_client import HaClient
from .mqtt_bridge import MqttBridge
from .ws_client import EufyWS


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Bridge:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.hb = cfg["homebase_sn"]
        self.cams = cfg["cameras"]              # {sn: {"key":..,"name":..}}
        self.poll = cfg.get("poll_interval", 10)
        self.motion_reset = cfg.get("motion_reset_seconds", 30)
        self.detector = MotionDetector()
        self.ws: EufyWS | None = None
        self.mqtt: MqttBridge | None = None
        self._motion_off_at: dict[str, float] = {}

        # concierge (live-view auto-idle) — optional
        self.concierge_enabled = bool(cfg.get("concierge_enabled", False)) and bool(cfg.get("ha_token"))
        self.concierge_interval = cfg.get("concierge_interval", 3)
        self._cc_streams = {                      # cam key -> [go2rtc stream names]
            meta["key"]: [sn] + ([meta["entity"]] if meta.get("entity") else [])
            for sn, meta in self.cams.items()
        }
        self._cc_entity = {meta["key"]: meta.get("entity") for meta in self.cams.values()}
        self.go2rtc: Go2rtc | None = None
        self.ha: HaClient | None = None
        self.concierge = Concierge(cfg.get("concierge_grace_seconds", 10))

        # mobile notification on motion (optional; needs HA API)
        self.notify_service = cfg.get("notify_service", "")
        self.notify_enabled = bool(self.notify_service) and bool(cfg.get("ha_token"))

    # -- setup ------------------------------------------------------------
    def start(self) -> None:
        self.ws = EufyWS(self.cfg["ws_host"], self.cfg.get("ws_port", 3000))
        self.mqtt = MqttBridge(self.cfg["mqtt_host"], self.cfg.get("mqtt_port", 1883),
                               self.cfg.get("mqtt_user", ""), self.cfg.get("mqtt_pass", ""))
        self.mqtt.connect()
        for sn, meta in self.cams.items():
            self.mqtt.announce_camera(meta["key"], meta["name"])
        self._seed_baseline()
        if self.concierge_enabled or self.notify_enabled:
            self.ha = HaClient(self.cfg["ha_url"], self.cfg["ha_token"])
        if self.concierge_enabled:
            self.go2rtc = Go2rtc(self.cfg["go2rtc_url"])
            print(f"[{_now_iso()}] concierge on: grace {self.concierge.grace}s", flush=True)
        if self.notify_enabled:
            print(f"[{_now_iso()}] notify on: {self.notify_service}", flush=True)
        print(f"[{_now_iso()}] bridge up: {len(self.cams)} cams, poll {self.poll}s", flush=True)

    def _notify_motion(self, key: str, name: str) -> None:
        if not self.notify_enabled:
            return
        image_entity = f"image.{key}_eufy2ha_letztes_event"
        picture = self.ha.get_entity_picture(image_entity)  # signed /api/image_proxy URL
        data = {"tag": f"eufy2ha_{key}", "group": "eufy2ha"}
        if picture:
            data["image"] = picture
        ok = self.ha.notify(self.notify_service, f"Bewegung: {name}",
                            "Bewegung erkannt", data)
        if ok:
            print(f"    notify -> {self.notify_service}", flush=True)

    def concierge_tick(self) -> None:
        if not self.concierge_enabled:
            return
        # viewers from go2rtc consumers; "live" (P2P running) from the HA camera
        # entity state — the go2rtc producer only turns real on-demand, but the
        # eufy integration marks camera.<x> "streaming" whenever P2P is up.
        viewers = self.go2rtc.states(self._cc_streams)
        if not viewers:
            return
        states: dict[str, tuple[bool, int]] = {}
        for cam, (_, v) in viewers.items():
            entity = self._cc_entity.get(cam)
            live = bool(entity) and self.ha.get_state(entity) == "streaming"
            states[cam] = (live, v)
        import time as _t
        for cam in self.concierge.evaluate(states, _t.time()):
            entity = self._cc_entity.get(cam)
            if entity and self.ha.stop_p2p(entity):
                print(f"[{_now_iso()}] concierge: {cam} 0 Zuschauer -> P2P gestoppt ({entity})",
                      flush=True)

    def _seed_baseline(self) -> None:
        data = self._query_latest(timeout=15)
        for item in data:
            sn = item.get("device_sn")
            if sn in self.cams and isinstance(item.get("event_count"), int):
                self.detector.seed(sn, item["event_count"])
                print(f"  baseline {self.cams[sn]['key']} = {item['event_count']}", flush=True)

    # -- ws helpers -------------------------------------------------------
    def _query_latest(self, timeout: float = 12) -> list[dict]:
        mid = self.ws.send({"command": "station.database_query_latest_info",
                            "serialNumber": self.hb})
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = self.ws.recv_json(timeout=max(1, end - time.time()))
            except (TimeoutError, socket.timeout):
                break
            if msg.get("type") == "event" and msg["event"].get("event") == "database query latest":
                return msg["event"].get("data", [])
        return []

    def _fetch_thumbnail(self, path: str, timeout: float = 15) -> bytes | None:
        self.ws.send({"command": "station.download_image",
                      "serialNumber": self.hb, "file": path})
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = self.ws.recv_json(timeout=max(1, end - time.time()))
            except (TimeoutError, socket.timeout):
                break
            if msg.get("type") != "event":
                continue
            if msg["event"].get("event") == "image downloaded":
                img = msg["event"].get("image") or msg["event"].get("picture") or {}
                data = img.get("data") if isinstance(img, dict) else None
                if isinstance(data, dict) and data.get("type") == "Buffer":
                    return bytes(data["data"])
                if isinstance(data, list):
                    return bytes(data)
        return None

    # -- main loop --------------------------------------------------------
    def run_once(self) -> None:
        self.mqtt.mark_online()   # self-heal a stale retained 'offline'
        data = self._query_latest()
        for ev in self.detector.update(data):
            meta = self.cams.get(ev.device_sn)
            if not meta:
                continue
            key = meta["key"]
            print(f"[{_now_iso()}] MOTION {key} count {ev.count} (+{ev.delta}) {ev.crop_path}",
                  flush=True)
            self.mqtt.publish_motion(key, True)
            self._motion_off_at[key] = time.time() + self.motion_reset
            self.mqtt.publish_event(key, _now_iso(), ev.count, ev.delta)
            if ev.crop_path:
                jpeg = self._fetch_thumbnail(ev.crop_path)
                if jpeg:
                    self.mqtt.publish_thumbnail(key, jpeg)
                    print(f"    thumbnail {len(jpeg)} bytes -> HA", flush=True)
                else:
                    print("    thumbnail download failed", flush=True)
            self._notify_motion(key, meta["name"])
        # auto-reset motion binary_sensors
        now = time.time()
        for key, off_at in list(self._motion_off_at.items()):
            if now >= off_at:
                self.mqtt.publish_motion(key, False)
                del self._motion_off_at[key]

    def run(self) -> None:
        self.start()
        tick = max(1, self.concierge_interval if self.concierge_enabled else self.poll)
        last_detect = 0.0
        while True:
            now = time.time()
            try:
                if now - last_detect >= self.poll:
                    last_detect = now
                    self.run_once()
                self.concierge_tick()
            except (ConnectionError, OSError) as e:
                print(f"[{_now_iso()}] WS error: {e}; reconnect in 5s", flush=True)
                time.sleep(5)
                self.ws = EufyWS(self.cfg["ws_host"], self.cfg.get("ws_port", 3000))
            time.sleep(tick)


def load_config() -> dict:
    here = os.path.dirname(__file__)
    path = os.path.join(here, "..", "config.json")
    cfg = json.load(open(path)) if os.path.exists(path) else {}
    # env overrides for secrets
    for env, key in (("MQTT_USERNAME", "mqtt_user"), ("MQTT_PASSWORD", "mqtt_pass"),
                     ("MQTT_BROKER", "mqtt_host"), ("HA_URL", "ha_url")):
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    # HA token: add-on supervisor token or dev token
    cfg["ha_token"] = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HA_TOKEN", "")
    return cfg


if __name__ == "__main__":
    Bridge(load_config()).run()
