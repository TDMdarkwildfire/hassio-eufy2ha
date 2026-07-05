"""Minimal stdlib WebSocket client for eufy-security-ws + the few commands the
bridge needs. No external deps (mirrors the proven probe client).

Commands used (all verified working on this HB2 + guest account):
  - station.database_query_latest_info -> per-device event_count + crop path
  - station.download_image             -> pull a thumbnail JPEG by path
"""
from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import threading


class EufyWS:
    def __init__(self, host: str, port: int = 3000, schema: int = 21):
        self._host, self._port, self._schema = host, port, schema
        self._id = 0
        self._lock = threading.Lock()
        self._connect()

    # -- connection / handshake -------------------------------------------
    def _connect(self) -> None:
        self.sock = socket.create_connection((self._host, self._port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET / HTTP/1.1\r\nHost: {self._host}:{self._port}\r\n"
                f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("handshake closed")
            resp += chunk
        if b" 101" not in resp.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"handshake failed: {resp[:120]!r}")
        self.buf = resp.split(b"\r\n\r\n", 1)[1]
        self.recv_json()  # version/hello
        self.send({"command": "set_api_schema", "schemaVersion": self._schema})
        self.send({"command": "start_listening"})

    # -- framing ----------------------------------------------------------
    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, obj: dict) -> str:
        with self._lock:
            self._id += 1
            obj = {"messageId": f"b-{self._id}", **obj}
            payload = json.dumps(obj).encode()
            mask = os.urandom(4)
            header = bytes([0x81])
            n = len(payload)
            if n < 126:
                header += bytes([0x80 | n])
            elif n < 65536:
                header += bytes([0x80 | 126]) + struct.pack(">H", n)
            else:
                header += bytes([0x80 | 127]) + struct.pack(">Q", n)
            self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
            return obj["messageId"]

    def recv_json(self, timeout: float | None = None):
        self.sock.settimeout(timeout)
        data, opcode = b"", None
        while True:
            hdr = self._read(2)
            fin, op = hdr[0] & 0x80, hdr[0] & 0x0F
            length = hdr[1] & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(length)
            if op == 0x9:      # ping -> ignore (server rarely pings a masked client)
                continue
            if op == 0x8:
                raise ConnectionError("server closed")
            if op != 0x0:
                opcode = op
            data += payload
            if fin:
                return json.loads(data.decode())

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass
