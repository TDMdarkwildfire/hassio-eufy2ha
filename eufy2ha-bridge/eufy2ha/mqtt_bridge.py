"""MQTT publisher with Home Assistant discovery for the eufy2ha bridge.

Per camera it exposes three entities, grouped under one HA device:
  - image        (last event thumbnail; raw JPEG bytes over image_topic)
  - binary_sensor (motion; ON pulse on a new recording, auto-OFF)
  - sensor        (last event timestamp; attributes: count, delta)

Entities key off a stable `unique_id` so they survive restarts and go
`unavailable` (not vanish) when the bridge is down (retained availability +
last-will).
"""
from __future__ import annotations

import json

import paho.mqtt.client as mqtt

DISCOVERY_PREFIX = "homeassistant"
BASE = "eufy2ha"


class MqttBridge:
    def __init__(self, host, port, username, password, on_command=None):
        self._avail = f"{BASE}/availability"
        self._client = mqtt.Client(client_id="eufy2ha-bridge")
        if username:
            self._client.username_pw_set(username, password)
        self._client.will_set(self._avail, "offline", retain=True)
        self._host, self._port = host, port
        self._connected = False

    def connect(self) -> None:
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()
        self.mark_online()
        self._connected = True

    def mark_online(self) -> None:
        """(Re)assert availability. Called on connect and every poll cycle so a
        stale retained 'offline' (e.g. another instance's last-will, or a broker
        restart) self-heals instead of stranding all entities as unavailable."""
        self._client.publish(self._avail, "online", retain=True)

    # -- discovery --------------------------------------------------------
    def announce_camera(self, cam_key: str, cam_name: str) -> None:
        """Publish HA discovery configs for one camera's three entities."""
        dev = {
            "identifiers": [f"{BASE}_{cam_key}"],
            "name": f"{cam_name} (eufy2ha)",
            "manufacturer": "eufy2ha",
            "model": "Polling bridge",
        }
        uid = f"{BASE}_{cam_key}"
        t = f"{BASE}/{cam_key}"

        image_cfg = {
            "name": "Letztes Event",
            "unique_id": f"{uid}_image",
            "image_topic": f"{t}/thumbnail",
            "content_type": "image/jpeg",
            "availability_topic": self._avail,
            "device": dev,
        }
        motion_cfg = {
            "name": "Bewegung",
            "unique_id": f"{uid}_motion",
            "state_topic": f"{t}/motion",
            "device_class": "motion",
            "payload_on": "ON",
            "payload_off": "OFF",
            "availability_topic": self._avail,
            "device": dev,
        }
        event_cfg = {
            "name": "Letztes Event",
            "unique_id": f"{uid}_event",
            "state_topic": f"{t}/event",
            "value_template": "{{ value_json.timestamp }}",
            "device_class": "timestamp",
            "json_attributes_topic": f"{t}/event",
            "availability_topic": self._avail,
            "device": dev,
        }
        self._pub(f"{DISCOVERY_PREFIX}/image/{uid}/config", image_cfg)
        self._pub(f"{DISCOVERY_PREFIX}/binary_sensor/{uid}/config", motion_cfg)
        self._pub(f"{DISCOVERY_PREFIX}/sensor/{uid}/config", event_cfg)

    # -- runtime updates --------------------------------------------------
    def publish_thumbnail(self, cam_key: str, jpeg: bytes) -> None:
        self._client.publish(f"{BASE}/{cam_key}/thumbnail", jpeg, retain=True)

    def publish_event(self, cam_key: str, timestamp: str, count: int, delta: int) -> None:
        payload = json.dumps({"timestamp": timestamp, "count": count, "delta": delta})
        self._client.publish(f"{BASE}/{cam_key}/event", payload, retain=True)

    def publish_motion(self, cam_key: str, on: bool) -> None:
        self._client.publish(f"{BASE}/{cam_key}/motion", "ON" if on else "OFF", retain=False)

    def _pub(self, topic: str, obj: dict) -> None:
        self._client.publish(topic, json.dumps(obj), retain=True)

    def close(self) -> None:
        if self._connected:
            self._client.publish(self._avail, "offline", retain=True)
            self._client.loop_stop()
            self._client.disconnect()
