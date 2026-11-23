"""BLE transport for the CarLinko T-box.

The pure helpers (:func:`frame`, :func:`parse`, :func:`crc16_arc`, :func:`encrypt_control`) have no
Home Assistant or bleak dependency; the connection helpers import them lazily.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# GATT characteristics used to talk to the T-box.
RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

CMD_STATUS = 0x77
CMD_FW_LOCATION = 0x23
CMD_FW_VERSION = 0x24

AES_KEY = bytes.fromhex("A0F47CB6677BE6A3")

STATE_BLOB_MIN_LEN = 72
STATUS_START_MARKER = 0x77
STATUS_SECOND_BYTE = 0x00


def is_status_blob(body: bytes, crc_ok: bool) -> bool:
    """A real status frame: good CRC, starts with ``77 00``, and at least the base length.

    Log frames start with ``77 02``; requiring both marker bytes keeps them out of telemetry.
    """
    return (
        crc_ok
        and len(body) >= STATE_BLOB_MIN_LEN
        and body[0] == STATUS_START_MARKER
        and body[1] == STATUS_SECOND_BYTE
    )

_CONNECT_TIMEOUT = 20.0
_REPLY_TIMEOUT = 8.0
_POST_CONTROL_DELAY = 2.0  # stay connected after a control so the car actuates and pushes new status


class CarLinkoBleError(Exception):
    """Base class for BLE transport errors."""


class CarLinkoBleUnavailable(CarLinkoBleError):
    """The car could not be reached over BLE: out of range, no scanner, or busy with the app."""


class CarLinkoBleRejected(CarLinkoBleError):
    """The car received the control but refused it (unregistered userId or unknown opcode)."""


# ---- pure protocol helpers (no HA / bleak) ----


def _code_hex(code: int | None) -> str:
    return "None" if code is None else f"0x{code:02x}"


def crc16_arc(data: bytes) -> int:
    """CRC-16/ARC: reflected polynomial 0xA001, init 0."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def frame(body: bytes, header: bytes = b"\x55\xaa") -> bytes:
    """Wrap a body in a frame with its length and CRC."""
    return header + len(body).to_bytes(2, "big") + body + crc16_arc(body).to_bytes(2, "big")


def parse(buf: bytes) -> tuple[list[tuple[bytes, bool]], bytes]:
    """Split a buffer into frames. Returns ``([(body, crc_ok), ...], leftover)``."""
    out: list[tuple[bytes, bool]] = []
    while True:
        hits = [j for j in (buf.find(b"\x55\xaa"), buf.find(b"\xaa\x55")) if j >= 0]
        i = min(hits) if hits else -1
        if i < 0 or len(buf) - i < 6:
            return out, buf[i:] if i >= 0 else b""
        n = int.from_bytes(buf[i + 2 : i + 4], "big")
        if len(buf) - i < 6 + n:
            return out, buf[i:]
        body = bytes(buf[i + 4 : i + 4 + n])
        crc = int.from_bytes(buf[i + 4 + n : i + 6 + n], "big")
        if n:
            out.append((body, crc == crc16_arc(body)))
        buf = buf[i + 6 + n :]


def _aes_ecb(key: bytes, data: bytes, decrypt: bool = False) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    cipher = Cipher(algorithms.AES(key), modes.ECB())
    op = cipher.decryptor() if decrypt else cipher.encryptor()
    return op.update(data) + op.finalize()


def encrypt_control(opcode: str, vin: str, user_id: str | int, rnd: bytes | None = None) -> bytes:
    """Build the control body the app sends over BLE."""
    rnd = rnd or os.urandom(8)
    pt = bytes.fromhex(opcode) + vin.encode() + str(user_id).encode()
    pt += b"\x00" * (-len(pt) % 16)
    return b"\x66" + rnd + _aes_ecb(AES_KEY + rnd, pt)


def encrypt_activate_key(vin: str, user_id: str | int, remaining: int, rnd: bytes | None = None) -> bytes:
    """Build the user-enroll command (``remaining`` = authorization seconds left; enrolment persists)."""
    rnd = rnd or os.urandom(8)
    pt = (
        bytes.fromhex("7801")
        + vin.encode()
        + str(user_id).encode()
        + b"\x00"
        + int(remaining).to_bytes(4, "big")
    )
    pt += b"\x00" * (-len(pt) % 16)
    return b"\x66" + rnd + _aes_ecb(AES_KEY + rnd, pt)


def decrypt_control(body: bytes) -> bytes:
    """Inverse of :func:`encrypt_control`."""
    if len(body) < 25 or body[0] != 0x66 or (len(body) - 9) % 16:
        raise ValueError("not a control body")
    return _aes_ecb(AES_KEY + body[1:9], body[9:], decrypt=True)


def device_name_from_sn(device_sn: str) -> str:
    """The car advertises as ``CHR`` + the last 8 characters of its deviceSn."""
    return "CHR" + device_sn[-8:]


# ---- connection layer (HA bluetooth stack + bleak) ----


class _Session:
    """One open BLE connection: feeds notifications through :func:`parse` into a queue."""

    def __init__(self, client) -> None:
        self._client = client
        self._buf = bytearray()
        self._queue: asyncio.Queue[tuple[bytes, bool]] = asyncio.Queue()

    def _on_notify(self, _char, data: bytearray) -> None:
        self._buf += bytes(data)
        frames, leftover = parse(bytes(self._buf))
        self._buf = bytearray(leftover)
        for body, ok in frames:
            self._queue.put_nowait((body, ok))

    async def start(self) -> None:
        await self._client.start_notify(TX, self._on_notify)

    def _drain(self) -> None:
        """Drop frames queued by a previous request, so this one can't match a stale reply."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover
                break

    async def _wait_for(
        self,
        prefix: int,
        timeout: float,
        validate: Callable[[bytes, bool], bool] | None = None,
    ) -> tuple[bytes, bool]:
        """Return the first frame starting with `prefix` that passes `validate`; others are skipped."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise CarLinkoBleUnavailable(f"no valid 0x{prefix:02x} reply within {timeout:.0f}s")
            try:
                body, ok = await asyncio.wait_for(self._queue.get(), remaining)
            except TimeoutError as err:
                raise CarLinkoBleUnavailable(f"no valid 0x{prefix:02x} reply within {timeout:.0f}s") from err
            if body and body[0] == prefix and (validate is None or validate(body, ok)):
                return body, ok

    async def query(self, opcode: int, timeout: float = _REPLY_TIMEOUT) -> tuple[bytes, bool]:
        self._drain()
        await self._client.write_gatt_char(RX, frame(bytes([opcode])), response=False)
        return await self._wait_for(opcode, timeout)

    async def read_status(self, timeout: float = _REPLY_TIMEOUT) -> bytes:
        self._drain()
        await self._client.write_gatt_char(RX, frame(bytes([CMD_STATUS])), response=False)
        body, _ok = await self._wait_for(CMD_STATUS, timeout, validate=is_status_blob)
        return body

    async def send_control(self, control_body: bytes, timeout: float = _REPLY_TIMEOUT) -> int | None:
        """Write a control and return the car's result code (``0x00`` = executed)."""
        self._drain()
        payload = frame(b"") + frame(control_body)
        await self._client.write_gatt_char(RX, payload, response=False)
        body, _ok = await self._wait_for(0x74, timeout)
        return body[3] if len(body) >= 4 else None

    async def activate_key(self, activate_body: bytes, timeout: float = _REPLY_TIMEOUT) -> bool:
        self._drain()
        payload = frame(b"") + frame(activate_body)
        await self._client.write_gatt_char(RX, payload, response=False)
        body, _ok = await self._wait_for(0x78, timeout)
        return len(body) >= 3 and body[1] == 0x01 and body[2] == 0x00


async def _do_handshake(session: _Session) -> bytes:
    """Run the init sequence the car expects on connect and return the status blob.

    Raises :class:`CarLinkoBleUnavailable` if the status does not come back.
    """
    await session.query(CMD_FW_LOCATION)
    await session.query(CMD_FW_VERSION)
    return await session.read_status()


@asynccontextmanager
async def _connect(hass: HomeAssistant, address: str, device_sn: str) -> AsyncIterator[_Session]:
    """Open a short-lived connection, yield a ready session, and always disconnect afterwards.

    The car accepts only one BLE client, so we connect, work and disconnect quickly, leaving it
    reachable from the phone app between polls.
    """
    from homeassistant.components import bluetooth

    device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if device is None:
        raise CarLinkoBleUnavailable(f"{address} not in BLE range")

    from bleak_retry_connector import (
        BleakClientWithServiceCache,
        establish_connection,
    )

    try:
        client = await establish_connection(
            BleakClientWithServiceCache,
            device,
            device_name_from_sn(device_sn),
            timeout=_CONNECT_TIMEOUT,
        )
    except Exception as err:
        raise CarLinkoBleUnavailable(f"connect to {address} failed: {err}") from err

    session = _Session(client)
    try:
        await session.start()
        yield session
    finally:
        try:
            await client.disconnect()
        except Exception:
            _LOGGER.debug("BLE disconnect from %s failed", address, exc_info=True)


async def async_read_state(hass: HomeAssistant, address: str, device_sn: str) -> str | None:
    """One sporadic telemetry read: connect, read the status blob, disconnect. Hex, or None."""
    from bleak.exc import BleakError

    try:
        async with _connect(hass, address, device_sn) as session:
            blob = await session.read_status()
            return blob.hex()
    except BleakError as err:
        raise CarLinkoBleUnavailable(f"BLE read from {address} failed: {err}") from err


async def async_send_control(
    hass: HomeAssistant,
    address: str,
    device_sn: str,
    vin: str,
    user_id: str | int,
    opcode: str,
    get_remaining: Callable[[], Awaitable[int | None]] | None = None,
) -> str | None:
    """One sporadic control: connect, handshake, send, enrol if needed, read result, close.

    On a not-enrolled reply the userId is enrolled (seconds from ``get_remaining``) and the control
    retried once. Returns the follow-up status hex (or None if it didn't arrive — the control still
    succeeded). Bleak failures map to :class:`CarLinkoBleUnavailable`; a refusal raises
    :class:`CarLinkoBleRejected`.
    """
    from bleak.exc import BleakError

    try:
        async with _connect(hass, address, device_sn) as session:
            await _do_handshake(session)
            _LOGGER.debug("BLE control %s: connected + handshake OK (%s)", opcode, address)
            control = encrypt_control(opcode, vin, user_id)
            code = await session.send_control(control)
            _LOGGER.debug("BLE control %s: car ack code=%s", opcode, _code_hex(code))

            if code == 0x44 and get_remaining is not None:
                remaining = await get_remaining()
                _LOGGER.debug("BLE control %s: not enrolled, enrolling (remaining=%s)", opcode, remaining)
                if remaining is not None and await session.activate_key(
                    encrypt_activate_key(vin, user_id, remaining)
                ):
                    code = await session.send_control(control)
                    _LOGGER.debug("BLE control %s: car ack after enrol code=%s", opcode, _code_hex(code))

            if code != 0x00:
                raise CarLinkoBleRejected(
                    f"car refused control (code={code}); "
                    f"{'userId not enrolled' if code == 0x44 else 'invalid opcode'}"
                )

            _LOGGER.debug("BLE control %s executed; reading follow-up status", opcode)
            await asyncio.sleep(_POST_CONTROL_DELAY)
            try:
                blob = await session.read_status()
                _LOGGER.debug("BLE control %s: follow-up status read (%d bytes)", opcode, len(blob))
                return blob.hex()
            except CarLinkoBleUnavailable:
                _LOGGER.debug("BLE control %s: follow-up status not captured; next poll will refresh", opcode)
                return None
    except BleakError as err:
        raise CarLinkoBleUnavailable(f"BLE control to {address} failed: {err}") from err
