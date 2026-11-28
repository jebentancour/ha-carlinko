"""Offline checks for blob decoding and capabilities parsing.

``blob.py`` does ``from .capabilities import ...``, so both are loaded under a synthetic
package (the real ``custom_components.carlinko`` package ``__init__`` pulls in Home Assistant)::

    python -m unittest discover tests
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest

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


capabilities = _load("capabilities")
blob = _load("blob")

# A synthetic status blob (73 bytes).
STATUS = (
    "7700000000000000000000000514000000000027100000000000000050012c00000000000000000000000000"
    "d2d2d2d26464646400000000000000000000000000000000012c012c00"
)


class BlobDecode(unittest.TestCase):
    def setUp(self) -> None:
        self.d = blob.decode_blob(STATUS)

    def test_known_values(self):
        self.assertFalse(self.d["lock_unlocked"])
        self.assertEqual(self.d["battery_pct"], 80)
        self.assertEqual(self.d["odometer_km"], 10000)
        self.assertEqual(self.d["volt12"], 13.0)
        self.assertEqual(self.d["tyre_psi"], [41.8, 41.8, 41.8, 41.8])
        self.assertEqual(self.d["charging_connector"], "disconnected")
        self.assertEqual(self.d["wltp_range_km"], 300)

    def test_short_blob_returns_empty(self):
        self.assertEqual(blob.decode_blob("7700"), {})

    def test_tpms_scale_applies(self):
        cfg = capabilities.parse_vehicle_control_config({"appKpaFormula": "data * 2.0"})
        scaled = blob.decode_blob(STATUS, cfg)
        # psi = raw * tpms_scale * 0.145; the config scale must be threaded through.
        raw = bytes.fromhex(STATUS)[44]
        self.assertEqual(scaled["tyre_psi"][0], round(raw * 2.0 * 0.145, 1))
        self.assertNotEqual(scaled["tyre_psi"][0], self.d["tyre_psi"][0])


class Plausibility(unittest.TestCase):
    def test_real_blob_is_plausible(self):
        self.assertTrue(blob.is_plausible(blob.decode_blob(STATUS)))

    def test_impossible_values_rejected(self):
        self.assertFalse(blob.is_plausible({"odometer_km": 9_000_000}))
        self.assertFalse(blob.is_plausible({"battery_pct": 250}))
        self.assertTrue(blob.is_plausible({"odometer_km": 7340}))


class FirmwareVersion(unittest.TestCase):
    def test_decodes_ascii_string(self):
        # 24 00 <ascii> 00
        reply = bytes.fromhex("2400") + b"1.2.3_000000A" + b"\x00"
        self.assertEqual(blob.parse_fw_version(reply), "1.2.3_000000A")

    def test_without_trailing_null(self):
        reply = bytes.fromhex("2400") + b"1.0.0"
        self.assertEqual(blob.parse_fw_version(reply), "1.0.0")

    def test_rejects_wrong_opcode_or_short(self):
        self.assertIsNone(blob.parse_fw_version(bytes.fromhex("230002")))  # fw-location, not version
        self.assertIsNone(blob.parse_fw_version(b"\x24"))  # too short
        self.assertIsNone(blob.parse_fw_version(None))
        self.assertIsNone(blob.parse_fw_version(bytes.fromhex("240000")))  # empty string


class Capabilities(unittest.TestCase):
    def test_flags_and_defaults(self):
        cfg = capabilities.parse_vehicle_control_config(
            {"Lock": 1, "Search": 1, "A/C": {"Switch": 1, "RapidHeat": 1}}
        )
        self.assertTrue(cfg.capabilities.lock)
        self.assertTrue(cfg.capabilities.find)
        self.assertTrue(cfg.capabilities.ac_switch)
        self.assertTrue(cfg.capabilities.ac_rapid_heat)
        self.assertFalse(cfg.capabilities.ac_rapid_cool)
        self.assertEqual(cfg.tpms_scale, capabilities.DEFAULT_TPMS_SCALE)

    def test_config_as_json_string(self):
        cfg = capabilities.parse_vehicle_control_config('{"Lock": 1}')
        self.assertTrue(cfg.capabilities.lock)

    def test_garbage_config_is_defaults(self):
        cfg = capabilities.parse_vehicle_control_config("not json")
        self.assertFalse(cfg.capabilities.lock)

    def test_decode_control_config_prefixes_flags(self):
        cfg = capabilities.parse_vehicle_control_config({"Lock": 1})
        flat = blob.decode_control_config(cfg)
        self.assertTrue(flat["control_lock"])
        self.assertIn("has_engine", flat)


if __name__ == "__main__":
    unittest.main()
