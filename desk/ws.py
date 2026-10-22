"""Minimal server side of RFC 6455 WebSockets - just enough for terminal streams."""

import base64
import hashlib
import json
import socket
import struct
import threading

_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_MESSAGE = 8 * 1024 * 1024

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class Closed(Exception):
    pass


def accept_value(key: str) -> str:
    return base64.b64encode(hashlib.sha1(key.encode() + _GUID).digest()).decode()


def _unmask(payload: bytes, mask: bytes) -> bytes:
    n = len(payload)
    if not n:
        return payload
    key = (mask * (n // 4 + 1))[:n]
    return (int.from_bytes(payload, "big") ^ int.from_bytes(key, "big")).to_bytes(n, "big")


class WebSocket:
    def __init__(self, sock: socket.socket, rfile):
        self._sock = sock
        self._rfile = rfile
        self._send_lock = threading.Lock()
        self.closed = False
        # A stalled browser must not block the PTY pump forever.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, struct.pack("ll", 10, 0))

    def _read(self, n: int) -> bytes:
        data = self._rfile.read(n)
        if data is None or len(data) < n:
            raise Closed()
        return data

    def _frame(self):
        b1, b2 = self._read(2)
        length = b2 & 0x7F
        if length == 126:
            (length,) = struct.unpack("!H", self._read(2))
        elif length == 127:
            (length,) = struct.unpack("!Q", self._read(8))
        if length > MAX_MESSAGE:
            raise Closed()
        mask = self._read(4) if b2 & 0x80 else None
        payload = self._read(length)
        if mask:
            payload = _unmask(payload, mask)
        return bool(b1 & 0x80), b1 & 0x0F, payload

    def recv(self):
        """Return the next message as (is_text, payload). Raises Closed."""
        kind, parts, size = None, [], 0
        while True:
            fin, opcode, payload = self._frame()
            if opcode == OP_CLOSE:
                self._send_quietly(OP_CLOSE, payload[:2])
                raise Closed()
            if opcode == OP_PING:
                self._send(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue
            if opcode in (OP_TEXT, OP_BINARY):
                kind, parts, size = opcode, [], 0
            elif opcode != OP_CONT or kind is None:
                raise Closed()
            parts.append(payload)
            size += len(payload)
            if size > MAX_MESSAGE:
                raise Closed()
            if fin:
                return kind == OP_TEXT, b"".join(parts)

    def _send(self, opcode: int, payload: bytes):
        n = len(payload)
        if n < 126:
            header = struct.pack("!BB", 0x80 | opcode, n)
        elif n < 65536:
            header = struct.pack("!BBH", 0x80 | opcode, 126, n)
        else:
            header = struct.pack("!BBQ", 0x80 | opcode, 127, n)
        with self._send_lock:
            if self.closed:
                raise OSError("websocket closed")
            self._sock.sendall(header + payload)

    def _send_quietly(self, opcode: int, payload: bytes = b""):
        try:
            self._send(opcode, payload)
        except OSError:
            pass

    def send_binary(self, data: bytes):
        self._send(OP_BINARY, data)

    def send_json(self, obj):
        self._send(OP_TEXT, json.dumps(obj).encode())

    def close(self):
        if not self.closed:
            self._send_quietly(OP_CLOSE, struct.pack("!H", 1000))
            self.closed = True

    def abort(self):
        """Drop the connection at once: the reader sees EOF and the browser reconnects."""
        self.closed = True
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
