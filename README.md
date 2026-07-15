# ha-carlinko

A native Home Assistant integration (`custom_components/carlinko`) for cars on the
**CarLinko** cloud (Jaecoo J5 EV, Omoda E5, and likely other Chery-group EVs).

Read-only by design — no remote control. Use only with your own account and car.

Reverse-engineered from and originally developed alongside
[j5-ev-dashboard](https://github.com/GodrezJr2/j5-ev-dashboard), a standalone dashboard for
the same cars — see that repo for the byte-level protocol notes (`docs/api-map.md`).

## Install

**HACS (custom repository):** add this repo's URL as a custom repository (category:
Integration), install "CarLinko", restart Home Assistant.

**Manual:** copy `custom_components/carlinko/` into your HA config's `custom_components/`
folder, restart Home Assistant.

Then: Settings → Devices & services → Add integration → **CarLinko**. Enter your CarLinko
email/password (a second account authorised on the car is recommended, since only one
session per account can be active at a time — logging in here can sign you out of the
official app on the primary account). The vehicle is auto-detected; if the account has more
than one car, you'll be asked to pick one.

## Entities

The car reports a single status blob (hex-encoded byte array) over its WebSocket. The
confirmed byte map was originally taken from the Jaecoo J5 EV, then extended and confirmed
with new fields on an Omoda E5.

| Entity | Byte(s) | Formula |
| --- | --- | --- |
| Battery % | 28 | raw |
| Range (km) | 29–30 | uint16 |
| Odometer (km) | 18–20 | uint24 |
| 12 V battery (V) | 12–13 | uint16 × 0.01 |
| Speed (km/h) | 14–15 | uint16 ÷ 16 |
| Consumption (kWh/100 km) | 55 | raw × 0.1 |
| Charge Power (kW) | 63, gated by byte 58 | raw × 0.1 if byte 58 == 1, else 0 |
| Regen Power (kW) | 63, gated by byte 58 | raw × 0.1 if byte 58 == 3, else 0 |
| Tyre pressure ×4 (psi) | 44–47 | raw × 1.373 × 0.145 (0xFF = n/a) |
| Tyre temperature ×4 (°C) | 48–51 | raw × 0.65 − 40 (0xFF = n/a) |
| Doors: driver / passenger / rear ×2 | 2, bitmask 0x01/0x02/0x04/0x08 | bit set = open |
| Trunk | 4 | nonzero = open |
| Online (binary_sensor) | — | derived: no fresh blob this poll |

Bytes 3, 5, 9, 57, 58, 59, 63 and 69 aren't confirmed enough for a proper sensor (or, for 63,
are already covered above but kept here too for byte-level cross-check) — they're exposed as
**diagnostic** entities with a working-hypothesis name (e.g. `Sunroof Position (byte 9)`)
instead of a generic `Raw Byte N`. Three of them (9, 63, 69) also get a display unit (%, kW,
kWh) since testing suggests an actual physical quantity — see `RAW_BYTE_LABELS`/`RAW_BYTE_UNITS`
in `sensor.py`. Once a byte is confirmed it graduates into a proper scaled sensor.

## Options

Settings → Devices & services → CarLinko → Configure lets you change the poll interval
(default 120 s, minimum 30 s — CarLinko's WebSocket has no documented rate limit, but stay
reasonable).

## Known limitations

- One WebSocket round-trip per poll (no persistent connection, no adaptive fast/slow
  cadence — simpler and fine for HA's coordinator model, but a driving session generates one
  data point per interval, not a continuous stream).
- Token is kept in memory only (not written to disk); a HA restart re-logs in from the
  stored email/password in the config entry.

## Security & privacy

Self-hosted, no server run by the author, no telemetry phoning home. Your CarLinko
email/password is stored only in HA's own config entry storage (encrypted at rest by HA
core) and sent only to CarLinko's own cloud (`*.hzhjcl.com`) over HTTPS/WSS to log in and
poll telemetry — exactly like the official app. No third-party backend, no analytics.

This is a hobby project with no warranty — see [LICENSE](LICENSE).
