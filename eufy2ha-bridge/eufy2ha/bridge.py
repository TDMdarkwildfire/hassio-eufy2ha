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

from .detector import MotionDetector
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

    # -- setup ------------------------------------------------------------
    def start(self) -> None:
        self.ws = EufyWS(self.cfg["ws_host"], self.cfg.get("ws_port", 3000))
        self.mqtt = MqttBridge(self.cfg["mqtt_host"], self.cfg.get("mqtt_port", 1883),
                               self.cfg.get("mqtt_user", ""), self.cfg.get("mqtt_pass", ""))
        self.mqtt.connect()
        for sn, meta in self.cams.items():
            self.mqtt.announce_camera(meta["key"], meta["name"])
        self._seed_baseline()
        print(f"[{_now_iso()}] bridge up: {len(self.cams)} cams, poll {self.poll}s", flush=True)

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
        # auto-reset motion binary_sensors
        now = time.time()
        for key, off_at in list(self._motion_off_at.items()):
            if now >= off_at:
                self.mqtt.publish_motion(key, False)
                del self._motion_off_at[key]

    def run(self) -> None:
        self.start()
        while True:
            try:
                self.run_once()
            except (ConnectionError, OSError) as e:
                print(f"[{_now_iso()}] WS error: {e}; reconnect in 5s", flush=True)
                time.sleep(5)
                self.ws = EufyWS(self.cfg["ws_host"], self.cfg.get("ws_port", 3000))
            time.sleep(self.poll)


def load_config() -> dict:
    here = os.path.dirname(__file__)
    path = os.path.join(here, "..", "config.json")
    cfg = json.load(open(path)) if os.path.exists(path) else {}
    # env overrides for secrets
    for env, key in (("MQTT_USERNAME", "mqtt_user"), ("MQTT_PASSWORD", "mqtt_pass"),
                     ("MQTT_BROKER", "mqtt_host")):
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    return cfg


if __name__ == "__main__":
    Bridge(load_config()).run()
