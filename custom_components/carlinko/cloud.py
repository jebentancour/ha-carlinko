"""Cloud transport for CarLinko: request signing, login and signed GET/POST.

This is the "cloud pipe". The protocol payloads it carries (remote-control opcodes, the status blob)
are decoded elsewhere; this module only signs requests, authenticates and moves bytes over HTTPS.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import aiohttp

from .const import (
    APP_LOGIN_BODY,
    APP_VERSION,
    CODE_TOKEN_EXPIRED,
    CODES_DEVICE_OFFLINE,
    SIGN_KEY,
    USER_AGENT,
)


class CarLinkoAuthError(Exception):
    """Login/credentials rejected."""


class CarLinkoAccountNotFoundError(CarLinkoAuthError):
    """Login rejected with code 10012: no account with this email in this region."""


class CarLinkoConnectionError(Exception):
    """Could not reach CarLinko."""


class CarLinkoDeviceOfflineError(CarLinkoConnectionError):
    """CarLinko accepted the request but the T-box has no cellular link (code 50043/50008)."""


class CarLinkoCommandError(CarLinkoConnectionError):
    """The cloud rejected a remote command for a reason other than the device being offline."""


def _now_ms() -> str:
    return str(int(time.time() * 1000))


def _sign(params: dict[str, Any]) -> str:
    m = {k: ("" if v is None else str(v)) for k, v in params.items()}
    ordered = {k: m[k] for k in sorted(m.keys())}
    msg = json.dumps(ordered, separators=(",", ":"), ensure_ascii=False).encode()
    return base64.b64encode(hmac.new(SIGN_KEY, msg, hashlib.sha256).digest()).decode()


def _headers_for(params: dict[str, Any], token: str | None = None) -> dict[str, str]:
    ts = _now_ms()
    h = {
        "timestamp": ts,
        "signature": _sign({**params, "timestamp": ts}),
        "user-agent": USER_AGENT,
        "language": "en",
    }
    if token:
        h["token"] = token
    return h


class CloudTransport:
    """Signed access to a single CarLinko account's REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        region: str,
        time_zone: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._region = region
        self._time_zone = time_zone
        self.token: str | None = None

    @property
    def api_base(self) -> str:
        return f"https://cqr-api-{self._region}.hzhjcl.com"

    async def login(self) -> str:
        """Log in with the stored account, return + cache the new session token."""
        body = {
            "account": self._email,
            "password": self._password,
            "dateTime": self._time_zone,
            "timeZone": self._time_zone,
            **APP_LOGIN_BODY,
        }
        ts = _now_ms()
        headers = {
            "timestamp": ts,
            "signature": _sign({**body, "timestamp": ts}),
            "user-agent": USER_AGENT,
            "content-type": "application/json",
            "language": "en",
            "version": APP_VERSION,
        }
        try:
            async with self._session.post(
                f"{self.api_base}/user/login", json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise CarLinkoConnectionError(str(err)) from err
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            raise CarLinkoConnectionError(f"non-JSON response from {self.api_base}: {text[:200]!r}") from err

        code = str(data.get("code"))
        if code == "10012":
            raise CarLinkoAccountNotFoundError(data.get("msg") or f"login failed: {data}")
        if code != "0000":
            raise CarLinkoAuthError(data.get("msg") or f"login failed: {data}")
        payload = data.get("data")
        token = payload if isinstance(payload, str) else (payload or {}).get("token")
        if not token:
            raise CarLinkoAuthError(f"login ok but no token in response: {data}")
        self.token = token
        return token

    async def signed_get(self, path: str, _retried: bool = False) -> dict[str, Any]:
        """GET a token-authed endpoint; re-logs in and retries once if the token has expired."""
        if not self.token:
            await self.login()
        headers = _headers_for({}, token=self.token)
        try:
            async with self._session.get(
                f"{self.api_base}{path}", headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise CarLinkoConnectionError(str(err)) from err
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            raise CarLinkoConnectionError(f"non-JSON response from {self.api_base}{path}: {text[:200]!r}") from err

        code = str(data.get("code"))
        if code == CODE_TOKEN_EXPIRED and not _retried:
            await self.login()
            return await self.signed_get(path, _retried=True)
        if code != "0000":
            raise CarLinkoConnectionError(data.get("msg") or f"request to {path} failed: {data}")
        return data

    async def _remote_control(
        self, vehicle_id: str, device_sn: str, data_hex: str, timeout: int = 20
    ) -> dict[str, Any]:
        """POST a payload to ``/remoteControl`` and return the accepted response JSON.

        The same payload travels identically over BLE and the cloud; the cloud echoes the car's reply
        in the response ``data`` field (``deviceSn__<hex>``). Raises on an offline or rejected result.
        """
        if not self.token:
            await self.login()
        body = {"vehicleId": vehicle_id, "deviceSn": device_sn, "data": data_hex, "timeOut": timeout}

        async def _post(token: str) -> dict[str, Any]:
            headers = _headers_for(body, token=token)
            headers["content-type"] = "application/json"
            try:
                async with self._session.post(
                    f"{self.api_base}/user/vehicle/remoteControl",
                    json=body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout + 8),
                ) as resp:
                    text = await resp.text()
            except aiohttp.ClientError as err:
                raise CarLinkoConnectionError(str(err)) from err
            try:
                return json.loads(text)
            except json.JSONDecodeError as err:
                raise CarLinkoConnectionError(f"non-JSON response from remoteControl: {text[:200]!r}") from err

        resp = await _post(self.token)
        # Only resend after an expired token: any other rejection may mean the car already got it.
        if str(resp.get("code")) == CODE_TOKEN_EXPIRED:
            resp = await _post(await self.login())
        code = str(resp.get("code"))
        if code in CODES_DEVICE_OFFLINE:
            raise CarLinkoDeviceOfflineError(resp.get("msg") or f"device offline (code {code})")
        if code != "0000":
            raise CarLinkoCommandError(resp.get("msg") or f"remoteControl command rejected: {resp}")
        return resp

    async def post_remote_control(
        self, vehicle_id: str, device_sn: str, payload_hex: str, timeout: int = 20
    ) -> str | None:
        """Send a control payload and return the car's reply hex (None if it sent none in time)."""
        return _reply_hex(await self._remote_control(vehicle_id, device_sn, payload_hex, timeout))

    async def query(
        self, vehicle_id: str, device_sn: str, opcode: str, timeout: int = 20
    ) -> str | None:
        """Issue a plain-text read opcode (``23``/``24``/``77``) and return the car's reply hex.

        The reply comes back in the response ``data`` field as ``deviceSn__<hex>``; this strips the
        prefix and returns the ``<hex>`` so it decodes byte-for-byte like a BLE reply.
        """
        return _reply_hex(await self._remote_control(vehicle_id, device_sn, opcode, timeout))


def _reply_hex(resp: dict[str, Any]) -> str | None:
    """The car's reply from a ``/remoteControl`` response ``data`` field (``deviceSn__<hex>``)."""
    reply = resp.get("data")
    if not isinstance(reply, str) or "__" not in reply:
        return None
    # The hex payload never contains "__"; take whatever follows the last one.
    return reply.rsplit("__", 1)[1] or None
