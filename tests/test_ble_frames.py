"""Offline checks for the BLE/cloud response-shape validation (Phase 1).

No Home Assistant, bleak or network. ``ble.py`` has no top-level HA/bleak/crypto imports, so it is
loaded straight from its file to avoid the package ``__init__`` (which pulls in Home Assistant)::

    python -m unittest discover tests
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest

# ble.py does `from .const import ...`, so load both under a synthetic package (the real
# custom_components.carlinko package __init__ pulls in Home Assistant).
_DIR = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "carlinko"
_PKG = "carlinko_offline"
if _PKG not in sys.modules:
    _pkg = types.ModuleType(_PKG)
    _pkg.__path__ = [str(_DIR)]
    sys.modules[_PKG] = _pkg


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{_PKG}.{name}", _DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{_PKG}.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("const")
ble = _load("ble")

# A synthetic status blob (73 bytes, parked and locked); not a real capture.
STATUS = (
    "7700000000000000000000000514000000000027100000000000000050012c00000000000000000000000000"
    "d2d2d2d26464646400000000000000000000000000000000012c012c00"
)
STATUS_BYTES = bytes.fromhex(STATUS)


def _reply(body: bytes, *, good_crc: bool = True) -> bytes:
    """Wrap a body as the car does (aa55 header). ``good_crc=False`` corrupts the trailing CRC."""
    buf = bytearray(ble.frame(body, header=b"\xaa\x55"))
    if not good_crc:
        buf[-1] ^= 0xFF
    return bytes(buf)


class _FakeClient:
    """Stands in for a bleak client: a write triggers the queued notification stream."""

    def __init__(self) -> None:
        self.session: ble._Session | None = None
        self.feed: bytes = b""

    async def start_notify(self, _char, _cb) -> None:
        pass

    async def write_gatt_char(self, _char, _data, response: bool = False) -> None:
        if self.feed and self.session is not None:
            stream, self.feed = self.feed, b""
            self.session._on_notify(None, bytearray(stream))


def _session_with(feed: bytes) -> tuple[ble._Session, _FakeClient]:
    client = _FakeClient()
    session = ble._Session(client)
    client.session = session
    client.feed = feed
    return session, client


class StatusShape(unittest.TestCase):
    def test_real_blob_lengths_accepted(self):
        self.assertTrue(ble.is_status_body(STATUS_BYTES))
        self.assertEqual(len(STATUS_BYTES), 73)
        self.assertTrue(ble.is_status_body(b"\x77\x00" + bytes(77)))  # 79-byte tail variant

    def test_log_frame_rejected(self):
        # 77 02 <ascii> debug log — right first byte, wrong second byte.
        self.assertFalse(ble.is_status_body(b"\x77\x02OK ready"))

    def test_short_and_wrong_length_rejected(self):
        self.assertFalse(ble.is_status_body(b"\x77\x00" + bytes(25)))  # ~27-byte partial
        self.assertFalse(ble.is_status_body(b"\x77\x00" + bytes(70)))  # 72 bytes, old threshold

    def test_crc_gate(self):
        self.assertTrue(ble.is_status_blob(STATUS_BYTES, True))
        self.assertFalse(ble.is_status_blob(STATUS_BYTES, False))


class ControlAndEnrolShape(unittest.TestCase):
    def test_control_ack(self):
        self.assertTrue(ble.is_control_ack(bytes.fromhex("74040000"), True))
        self.assertFalse(ble.is_control_ack(bytes.fromhex("74040000"), False))  # bad CRC
        self.assertFalse(ble.is_control_ack(bytes.fromhex("740400"), True))  # too short
        self.assertFalse(ble.is_control_ack(b"\x74" + bytes(26), True))  # 27-byte frame

    def test_enrol_ack(self):
        self.assertTrue(ble.is_enrol_ack(bytes.fromhex("780100"), True))
        self.assertFalse(ble.is_enrol_ack(bytes.fromhex("780100"), False))  # bad CRC
        self.assertFalse(ble.is_enrol_ack(bytes.fromhex("7801"), True))  # too short

    def test_query_reply(self):
        self.assertTrue(ble.is_query_reply(0x24, bytes.fromhex("2401"), True))
        self.assertFalse(ble.is_query_reply(0x24, bytes.fromhex("2401"), False))  # bad CRC
        self.assertFalse(ble.is_query_reply(0x24, bytes.fromhex("24"), True))  # opcode only


class ReadStatusStream(unittest.TestCase):
    def test_only_the_real_blob_is_accepted(self):
        # A log frame, a 27-byte partial that also starts 0x77, then the real blob — in that order.
        log = _reply(b"\x77\x02OK status log line")
        partial = _reply(b"\x77\x00" + bytes(25))
        real = _reply(STATUS_BYTES)
        session, _client = _session_with(log + partial + real)
        body = asyncio.run(session.read_status(timeout=1.0))
        self.assertEqual(body, STATUS_BYTES)

    def test_no_real_blob_times_out(self):
        session, _client = _session_with(_reply(b"\x77\x02just a log"))
        with self.assertRaises(ble.CarLinkoBleUnavailable):
            asyncio.run(session.read_status(timeout=0.3))


class SendControlStream(unittest.TestCase):
    def test_good_ack_returns_result_code(self):
        session, _client = _session_with(_reply(bytes.fromhex("74040000")))
        code = asyncio.run(session.send_control(bytes.fromhex("66" + "00" * 24), timeout=1.0))
        self.assertEqual(code, 0x00)

    def test_bad_crc_74_frame_not_taken_as_ack(self):
        # A 74-prefixed frame with a corrupt CRC must not be mistaken for the control ACK.
        session, _client = _session_with(_reply(bytes.fromhex("74040000"), good_crc=False))
        with self.assertRaises(ble.CarLinkoBleUnavailable):
            asyncio.run(session.send_control(bytes.fromhex("66" + "00" * 24), timeout=0.3))

    def test_short_74_frame_skipped_until_real_ack(self):
        stray = _reply(b"\x74" + bytes(26))  # 27-byte frame starting 0x74
        good = _reply(bytes.fromhex("74050044"))  # 74 CMD SS code, code=0x44
        session, _client = _session_with(stray + good)
        code = asyncio.run(session.send_control(bytes.fromhex("66" + "00" * 24), timeout=1.0))
        self.assertEqual(code, 0x44)


class CloudDefenseInDepth(unittest.TestCase):
    """The cloud path (api._get_state) gates on is_status_body before decoding — same function."""

    def test_non_status_cloud_response_rejected(self):
        # A `77 02 ...`-shaped hex payload (not a status blob) must not pass the decode gate.
        self.assertFalse(ble.is_status_body(bytes.fromhex("7702" + "41" * 20)))

    def test_real_cloud_blob_accepted(self):
        self.assertTrue(ble.is_status_body(STATUS_BYTES))


if __name__ == "__main__":
    unittest.main()
