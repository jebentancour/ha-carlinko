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

The car reports a single status blob (hex-encoded byte array) via a plain signed REST GET.
The confirmed byte map was originally taken from the Jaecoo J5 EV, then extended and
confirmed with new fields on an Omoda E5.

| Entity | Byte(s) | Formula |
| --- | --- | --- |
| Doors: driver / passenger / rear ×2 | 2, bitmask 0x01/0x02/0x04/0x08 | bit set = open |
| Lock | 3 | nonzero = unlocked |
| Trunk | 4 | nonzero = open |
| Ignition | 5 | nonzero = on |
| Windows: driver / passenger / rear ×2 | 8, 2 bits each (0xC0/0x30/0x0C/0x03) | any bit set = open |
| Sunroof | 9 | nonzero = open |
| 12 V battery (V) | 12–13 | uint16 × 0.01 |
| Speed (km/h) | 14–15 | uint16 ÷ 16 |
| Odometer (km) | 18–20 | uint24 |
| Battery % | 28 | raw |
| Range (km) | 29–30 | uint16 |
| Tyre pressure ×4 (psi) | 44–47 | raw × 1.373 × 0.145 (0xFF = n/a) |
| Tyre temperature ×4 (°C) | 48–51 | raw × 0.65 − 40 (0xFF = n/a) |
| Consumption (kWh/100 km) | 55 | raw × 0.1 |
| Diagnostic: Charge Cable Connected (byte 56) | 56 | raw (0=unplugged, 1=plugged in) |
| Diagnostic: Charge Port / EVSE State (byte 57) | 57 | raw |
| Diagnostic: Charging Flag (byte 58) | 58 | raw |
| Diagnostic: Charge Counter (byte 59) | 59 | raw |
| Charge Power (kW) | 63, gated by byte 58 | raw × 0.1 if byte 58 == 1, else 0 |
| Regen Power (kW) | 63, gated by byte 58 | raw × 0.1 if byte 58 == 3, else 0 |
| Diagnostic: Power (byte 63) | 63 | raw × 0.1 kW (same byte as charge/regen, kept for cross-check) |
| Diagnostic: Trip Energy Used (bytes 68:69) | 68–69 | uint16, 68<<8\|69, scale unconfirmed |
| Diagnostic: Trip Range (bytes 70:71) | 70–71 | uint16, 70<<8\|71, unconfirmed |

Byte 5 (ignition) is confirmed enough to be a proper binary sensor; bytes 56, 57, 58, 59 and
63 aren't (or, for 63, are already covered above but kept here too for byte-level cross-check)
— they're exposed as **diagnostic** entities with a working-hypothesis name instead of a
generic `Raw Byte N`. Byte 63 also gets a display unit (kW) since testing suggests an actual
physical quantity — see `RAW_BYTE_LABELS`/`RAW_BYTE_UNITS` in `sensor.py`. Bytes 68:69 and
70:71 are combined into two 16-bit diagnostic values instead (see `RAW_WORD_LABELS` /
`RAW_WORD_PAIRS`) since the working hypothesis treats each pair as one field, not two.
Once a byte (or pair) is confirmed it graduates into a proper scaled sensor.

**Online** (`binary_sensor`) isn't part of the status blob — it comes from a separate
endpoint, `GET /user/vehicle/isOnline/{id}`, polled once per cycle alongside `state`. When
it reports offline, the coordinator skips the blob fetch and keeps the last known values
for every other entity instead of clearing them.

## Options

Settings → Devices & services → CarLinko → Configure lets you change the poll interval
(default 120 s, minimum 30 s — CarLinko's REST API has no documented rate limit, but stay
reasonable).

## Known limitations

- Two signed REST GETs per poll (`isOnline` + `state`, no persistent connection, no adaptive
  fast/slow cadence — simpler and fine for HA's coordinator model, but a driving session
  generates one data point per interval, not a continuous stream).
- Token is kept in memory only (not written to disk); a HA restart re-logs in from the
  stored email/password in the config entry.

## Security & privacy

Self-hosted, no server run by the author, no telemetry phoning home. Your CarLinko
email/password is stored only in HA's own config entry storage (encrypted at rest by HA
core) and sent only to CarLinko's own cloud (`*.hzhjcl.com`) over HTTPS/WSS to log in and
poll telemetry — exactly like the official app. No third-party backend, no analytics.

This is a hobby project with no warranty — see [LICENSE](LICENSE).
