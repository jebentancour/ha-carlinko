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

| Entity | Status |
| --- | --- |
| Battery %, Range, Odometer | confirmed |
| 12 V battery, Speed, Consumption | confirmed |
| Tyre pressure / temperature ×4 wheels | confirmed |
| Doors (driver/passenger/rear ×2) + Trunk (binary_sensor) | confirmed |
| Charge Power / Regen Power | confirmed |
| Online (binary_sensor) | derived (no fresh blob this poll) |

This integration only ships **confirmed** fields — byte offset + formula validated against
a real car's own dash/app display or a deliberate test (open/close one door or the trunk at
a time and watch which byte moves), not just internal consistency. The confirmed set was
originally calibrated on a Jaecoo J5 EV, then independently re-validated bit-for-bit against
an **Omoda E5** (battery/range/odometer/12V/speed/consumption/tyre PSI+temp all matched the
app's own numbers exactly); doors + trunk were confirmed the same way on the Omoda E5 (byte
2 is a 4-bit door mask, byte 4 is the trunk), and power (byte 63 × 0.1) matched the app's
displayed kW, during a real charge session. That same byte also
spikes from regen/braking while driving, so it's split into two sensors using byte 58
(1=charging, else not) — Charge Power is non-zero only while plugged in and charging, Regen
Power only while driving — see `api.py`'s `decode_blob()` docstring.

There are a handful of other bytes in the blob that visibly change with car state
(driving/braking/climate/charging) but aren't fully confirmed yet. The most promising ones —
bytes 3, 5, 9, 57, 58, 59, 63, 69 — are exposed as **diagnostic** entities (`Raw Byte N`,
grouped under the device's "diagnostic" section, enabled by default), so hypotheses can be
tested live in HA. Their raw integer value is shown as-is, unscaled — see `api.py`'s
`decode_blob()` docstring for what each is suspected to mean. Once a field is confirmed it
graduates into a proper scaled sensor and the raw one can be removed.

## Options

Settings → Devices & services → CarLinko → Configure lets you change the poll interval
(default 120 s, minimum 30 s — CarLinko's WebSocket has no documented rate limit, but stay
reasonable).

## Known limitations

- One WebSocket round-trip per poll (no persistent connection, no adaptive fast/slow
  cadence — simpler and fine for HA's coordinator model, but a driving session generates one
  data point per interval, not a continuous stream).
- No charging-session detection yet — out of scope for v0.1.
- Token is kept in memory only (not written to disk); a HA restart re-logs in from the
  stored email/password in the config entry.

## Security & privacy

Self-hosted, no server run by the author, no telemetry phoning home. Your CarLinko
email/password is stored only in HA's own config entry storage (encrypted at rest by HA
core) and sent only to CarLinko's own cloud (`*.hzhjcl.com`) over HTTPS/WSS to log in and
poll telemetry — exactly like the official app. No third-party backend, no analytics.

This is a hobby project with no warranty — see [LICENSE](LICENSE).
