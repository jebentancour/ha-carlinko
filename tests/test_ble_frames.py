"""Offline checks for the BLE/cloud response-shape validation.

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

# A synthetic status blob (73 bytes, parked and locked).
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
        self.assertFalse(ble.is_status_body(b"\x77\x02debug text"))

    def test_short_and_wrong_length_rejected(self):
        self.assertFalse(ble.is_status_body(b"\x77\x00" + bytes(25)))  # ~27-byte partial
        self.assertFalse(ble.is_status_body(b"\x77\x00" + bytes(70)))  # 72 bytes, one short

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


class _ScriptedSession:
    """A connected session whose control/status calls return or raise from a script."""

    def __init__(self, control) -> None:
        self.control = control
        self.controls = 0

    async def send_control(self, _body):
        self.controls += 1
        if isinstance(self.control, Exception):
            raise self.control
        return self.control

    async def read_status(self):
        return STATUS_BYTES


class SendControlOutcome(unittest.TestCase):
    """Only a failure before the control is written may be resent over the cloud."""

    def setUp(self):
        from contextlib import asynccontextmanager

        if "bleak.exc" not in sys.modules:
            bleak_exc = types.ModuleType("bleak.exc")
            bleak_exc.BleakError = type("BleakError", (Exception,), {})
            sys.modules.setdefault("bleak", types.ModuleType("bleak"))
            sys.modules["bleak.exc"] = bleak_exc
        self._saved = (ble._connect, ble.encrypt_control, ble._POST_CONTROL_DELAY)
        ble.encrypt_control = lambda opcode, vin, user_id: bytes.fromhex(opcode)
        ble._POST_CONTROL_DELAY = 0
        self.session = None
        self.connect_error = None

        @asynccontextmanager
        async def fake_connect(_hass, _address, _sn):
            if self.connect_error:
                raise self.connect_error
            yield self.session

        ble._connect = fake_connect

    def tearDown(self):
        ble._connect, ble.encrypt_control, ble._POST_CONTROL_DELAY = self._saved

    def _send(self):
        return asyncio.run(ble.async_send_control(None, "addr", "sn", "VIN", "1", "740600"))

    def test_not_connected_is_unavailable(self):
        self.connect_error = ble.CarLinkoBleUnavailable("not in range")
        with self.assertRaises(ble.CarLinkoBleUnavailable):
            self._send()

    def test_sent_without_ack_is_no_reply(self):
        self.session = _ScriptedSession(ble.CarLinkoBleUnavailable("no valid 0x74 reply"))
        with self.assertRaises(ble.CarLinkoControlNoReply):
            self._send()
        self.assertEqual(self.session.controls, 1)

    def test_link_dropped_after_send_is_no_reply(self):
        self.session = _ScriptedSession(sys.modules["bleak.exc"].BleakError("disconnected"))
        with self.assertRaises(ble.CarLinkoControlNoReply):
            self._send()

    def test_executed_returns_status(self):
        self.session = _ScriptedSession(0x00)
        self.assertEqual(self._send(), STATUS)

    def test_refused_is_rejected(self):
        self.session = _ScriptedSession(0x97)
        with self.assertRaises(ble.CarLinkoBleRejected):
            self._send()


class RefusalReason(unittest.TestCase):
    def test_known_code_carries_reason(self):
        err = ble.CarLinkoBleRejected(0x97)
        self.assertEqual((err.code, err.reason), (0x97, "trunk_open"))
        self.assertIn("0x97", str(err))

    def test_unknown_code_has_no_reason(self):
        err = ble.CarLinkoBleRejected(0xEE)
        self.assertIsNone(err.reason)
        self.assertIn("0xee", str(err))

    def test_control_result_code(self):
        self.assertEqual(ble.control_result_code(bytes.fromhex("74050000")), 0x00)
        self.assertEqual(ble.control_result_code(bytes.fromhex("7405002b")), 0x2B)
        self.assertEqual(ble.control_result_code(bytes.fromhex("7404")), 0x04)
        self.assertIsNone(ble.control_result_code(bytes.fromhex("780100")))
        self.assertIsNone(ble.control_result_code(b""))

    def test_ble_refusal_is_a_control_refusal(self):
        self.assertIsInstance(ble.CarLinkoBleRejected(0x97), ble.CarLinkoControlRejected)

    def test_every_reason_is_translated(self):
        import json

        for lang in ("strings.json", "translations/en.json", "translations/es.json"):
            exceptions = json.loads((_DIR / lang).read_text())["exceptions"]
            for reason in set(const.CONTROL_RESULT_REASONS.values()):
                self.assertIn(f"refused_{reason}", exceptions, lang)


class CloudDefenseInDepth(unittest.TestCase):
    """The unified read (api._decode_candidate) gates on is_status_body before decoding — same function."""

    def test_non_status_cloud_response_rejected(self):
        # A `77 02 ...`-shaped hex payload (not a status blob) must not pass the decode gate.
        self.assertFalse(ble.is_status_body(bytes.fromhex("7702" + "41" * 20)))

    def test_real_cloud_blob_accepted(self):
        self.assertTrue(ble.is_status_body(STATUS_BYTES))


if __name__ == "__main__":
    unittest.main()
