# ha-carlinko

A native Home Assistant integration (`custom_components/carlinko`) for cars on the
**CarLinko** cloud (Jaecoo J5 EV, Omoda E5, and likely other Chery-group EVs).

Mostly read-only — telemetry only, plus a couple of remote-control buttons (Stop Charging,
Find Car) on cars that support them. Use only with your own account and car.

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

The car reports a single status blob (hex-encoded byte array) via a signed endpoint,
`GET /user/vehicle/state/{id}`. The confirmed byte map was originally taken from the Jaecoo
J5 EV, then extended and confirmed with new fields on an Omoda E5.

Fuel Level, Fuel Consumption and Power Consumption are only created on vehicles whose
`vehicleControlConfig` reports the matching flag (`Engine`, `fuelConsumption`,
`powerConsumption` respectively) — a pure BEV won't get entities that would always read 0.

| Entity | Byte(s) | Formula |
| --- | --- | --- |
| Doors: front left / front right / rear left / rear right | 2, bitmask 0x01/0x02/0x04/0x08 | bit set = open |
| Lock | 3 | nonzero = unlocked |
| Raw Byte 3 *(diagnostic)* | 3 | raw value alongside the `Lock` bool above, for visibility into any non-0/1 values |
| Liftgate | 4 | nonzero = open |
| Ignition | 5 | nonzero = on |
| Raw Byte 5 *(diagnostic)* | 5 | raw value alongside the `Ignition` bool above — possible `>=2` HV/motor-state threshold instead of any-nonzero, unconfirmed |
| Windows: front left / front right / rear left / rear right | 8, 2 bits each (0xC0/0x30/0x0C/0x03) | enum per window: 00=closed, 01=open, 10=vent, 11=open (fallback) |
| Sunroof | 9 | enum: 0x00=closed, 0x08=open, 0x0B=tilted (vent), else=open |
| 12 V battery (V) | 12–13 | uint16 × 0.01 |
| Speed (km/h) | 14–15 | uint16 ÷ 16 |
| Odometer (km) | 18–20 | uint24 |
| Fuel Level % *(only if `Engine` is set)* | 21 | raw |
| AC / climate on (`climate` entity) | 23 | nonzero = on |
| Climate Target Temperature (°C) (`climate` entity) | 24 | raw |
| Battery Level % | 28 | raw |
| Battery Range (km) | 29–30 | uint16 |
| Seat Heating/Ventilation Left / Right (`fan` entities) | 32, 33 / 37, 38 | enum: 0=off, 1=low, 2=medium, 3=high |
| Front Defroster | 42 | nonzero = on |
| Tyre pressure ×4 (psi) | 44–47 | raw × scale × 0.145, scale/invalid sentinel from `vehicleControlConfig` (default: 1.373, 0xFF = n/a) |
| Tyre temperature ×4 (°C) | 48–51 | raw × 0.65 − 40, invalid sentinel from `vehicleControlConfig` (default: 0xFF = n/a) |
| Fuel Consumption (L/100 km) *(only if `fuelConsumption` is set)* | 53 | raw × 0.1 |
| Power Consumption (kWh/100 km) *(only if `powerConsumption` is set)* | 55 | raw × 0.1 |
| Charging Connector | 56 | enum: 0=disconnected, 1=AC(slow), 16=DC(fast), else=disconnected |
| Charging Status / Charging (binary) | 57 | enum: 0=idle, 1=charging, 2=complete, 3=canceled, 4=hot, 5=stopping — `charging` = (57 != idle) |
| Charging Time Remaining (min) | 58–59 | uint16, 58<<8\|59, invalid sentinel(s) from `vehicleControlConfig` (default: 0x3FE/0x3FF/0x7FE/0x7FF = n/a) |
| Power (kW) | 62–63 | (62<<8\|63) × 0.1 |
| Charge Power (kW) | 62–63, gated by byte 57 | Power if charging, else 0 |
| Regen Power (kW) | 62–63, gated by byte 57 | Power if not charging, else 0 |
| Raw Byte 67 *(diagnostic)* | 67 | raw, meaning unconfirmed (varies 0x00/0x02/0xFF) — candidate for reflecting Quick Heat/Cool state |
| WLTP Range (km) | 68–69 | uint16 |
| Range (km) | 70–71 | uint16 |

**Online** (`binary_sensor`) isn't part of the status blob — it comes from a separate
endpoint, `GET /user/vehicle/isOnline/{id}`, polled once per cycle alongside `state`. When
it reports offline, the coordinator skips the blob fetch and keeps the last known values
for every other entity instead of clearing them.

### Powertrain & capabilities

The account endpoint `GET /user/vehicle` also publishes per-model constants and feature
flags in `vehicleControlConfig` — fetched once and cached for the life of the config entry
(it's not part of the polled status blob). This drives the tyre-pressure scale/invalid
sentinels and charging-time invalid sentinels above. `A/C.SetTemperatureMin/Max` and
`A/C.TemperatureStepValue` used to back their own `Control: A/C Min/Max Temperature`/
`Temperature Step` diagnostic sensors; they're now internal-only, feeding `climate.<vehicle>_ac`'s
`min_temp`/`max_temp`/`target_temperature_step` (see below) without a separate entity of
their own.

Every other `vehicleControlConfig` capability flag has by now either been folded into gating
one of the entities in [Controls](#controls) below, or removed outright as unused (the
trip-schedule entities from `terminalNoticeConfig`; `Control: Charging Power`, which
originally checked the wrong key — `chargingPower` instead of `ChargingManagement` — and is
now fixed and used to gate the Stop Charging button instead; `Control: Scheduled Charging/Trip
Supported`; `Control: A/C Pre-condition Duration`). None of the diagnostic `Control: *`
binary_sensors remain — `CONTROL_CAPABILITY_SENSORS` in `binary_sensor.py` is intentionally
empty, kept as a mechanism for any future capability flag that doesn't map to an actuator.

## Controls

`vehicleControlConfig` flags (see above) gate the entities below, each only created on cars
that report support for the matching flag. Every command is the same `POST
/user/vehicle/remoteControl` request the official app sends, signed the same way as every
other request this integration already makes. CarLinko's HTTP response only confirms the
command was accepted for delivery — the actual result comes back over CarLinko's WebSocket,
which this integration doesn't hold open, so there's no in-HA confirmation the car actually
did the thing beyond re-polling telemetry right after.

- **Stop Charging** (`button.<vehicle>_stop_charging`, gated by `ChargingManagement`,
  opcode `742701`) — triggers a telemetry refresh right after pressing, so
  `charging`/`charging_status` should reflect it within a poll or two.
- **Find Car** (`button.<vehicle>_find_car`, gated by `Search`, opcode `740400`) — no
  telemetry signature to check against (it's a honk/flash), so pressing it is fire-and-forget.
- **Lock** (`lock.<vehicle>_lock`, gated by `Lock`, opcodes `740100`/`740200`) — reads byte 3
  of the status blob (same field the old read-only `Lock` binary_sensor used) and calls
  lock/unlock on demand; state updates on the next telemetry poll after a command, so may lag
  a few seconds behind the car actually (un)locking.
- **Liftgate** (`cover.<vehicle>_liftgate`, gated by `PowerLiftgate`, opcodes `740300`/`740A00`)
  — a `cover` entity (open/close only, no position), reads byte 4 (same field the old
  read-only `Liftgate` binary_sensor used) and calls open/close on demand; same telemetry-lag
  caveat as Lock above.
- **Sunroof** (`cover.<vehicle>_sunroof`, gated by `Sunroof`, opcodes `740F01`/`740F00`) — a
  `cover` entity, reads byte 9's closed/open/tilted enum (see above; same field the old
  read-only `Sunroof` binary_sensor used, now with the tilted state distinguished from fully
  open). If the car's config also reports `SunroofTilting`, the entity additionally exposes
  tilt open/close (opcode `740F02` for vent, `740F00` for closing back down — there's no
  distinct "leave closed but untilt" opcode, so closing the tilt and closing outright are the
  same command) and reports the tilted state as `current_cover_tilt_position` (100 when
  tilted, 0 otherwise — there's no graduated position, just the three states). Same
  telemetry-lag caveat as Lock above.
- **Windows** (`cover.<vehicle>_window_{front,rear}_{left,right}`, gated by
  `WindowsOpen`/`WindowsClose`, opcodes `740600`/`740500`) — 4 `cover` entities, one per
  window, each reading its own 2-bit closed/open/vent state from byte 8 (same field the old
  read-only `Window *` binary_sensors used). **CarLinko only has a single all-windows opcode,
  not a per-window one** — opening/closing/venting *any* one of the 4 entities moves every
  window on the car, not just that one; they're separate entities purely so each can report
  its own individual state. If the car's config also reports `WindowsVent`, all 4 additionally
  expose tilt open/close (opcode `740E00` for vent; closing the tilt reuses the plain close
  opcode, same reasoning as Sunroof above). Same telemetry-lag caveat as Lock above.
- **Front Defroster** (`switch.<vehicle>_defrost_front`, gated by `A/C.Defogging`, opcodes
  `741201`/`741200`) — a `switch` entity, reads byte 42 (same field the old read-only
  `Front Defroster` binary_sensor used) and calls on/off on demand.
- **Seat heating/ventilation** (`fan.<vehicle>_seat_{heat,vent}_{left,right}`, gated by
  `A/C.DriverHeater`/`AssistantHeater`/`DriverVent`/`AssistantVent` respectively) — 4 `fan`
  entities (not 1 combined entity with heat/cool preset modes, since heat and vent are
  independent bytes/opcodes per seat and nothing confirms they're mutually exclusive on this
  car), each reading its own 2-bit low/medium/high/off level from bytes 32/33 (heat) or 37/38
  (vent) — same fields the old `Seat Heating/Ventilation Left/Right` sensors used — mapped to
  a 3-speed `percentage` (33/67/100%, `speed_count=3`). Opcodes: seat heat left/right
  `741501-03`/`741601-03` (off `741500`/`741600`), seat vent left/right `741A01-03`/`741B01-03`
  (off `741A00`/`741B00`).
- **A/C** (`climate.<vehicle>_ac`, gated by `A/C.Switch`) — combines A/C power, target
  temperature and Quick Heat/Cool into one `climate` entity, reading bytes 23/24 (same fields
  the old `AC / climate on` binary_sensor and `Climate Target Temperature` sensor used).
  **Power is writable**: selecting `off` calls the plain A/C off opcode (`741000`); `hvac_mode`
  reports `off` (A/C off), `heat`/`cool` (A/C on, target pinned to this car's max/min — same
  inference Quick Heat/Cool used before, see byte 67 note above), or `auto` (A/C on, neither
  extreme). `HEAT`/`COOL` are only offered if `A/C.RapidHeat`/`RapidCool` are set, and calling
  them fires the confirmed Quick Heat/Cool opcodes (`741F01`/`742001`); selecting `auto` calls
  A/C on (`741001`, covers the Off→Auto transition) plus both "quick off" opcodes
  (`741F00`+`742000`, harmless if one was already off) to cancel whichever quick mode is
  active, without touching the temperature.
  **Target temperature is also writable** (only if `A/C.SetTemperature` is set): the `7411` +
  2-hex-digit payload command's encoding is decoded — whole-degree (`raw = tempC`) or
  half-degree (`raw = (tempC × 2) | 0x80`) steps depending on this car's own
  `A/C.TemperatureStepValue` (`1` on this account = whole-degree, so e.g. 21°C → `741115`).
  **None of the A/C on/off/temperature opcodes have been fired live yet** (unlike Quick
  Heat/Cool) — treat them as decoded-not-confirmed like the Front Defroster and seat opcodes
  were before the user tested those.

## Options

Settings → Devices & services → CarLinko → Configure lets you change:

- **Poll interval** (default 120 s, minimum 30 s) — how often the telemetry blob (`isOnline` +
  `state`) is fetched.

CarLinko's REST API has no documented rate limit, but stay reasonable.

## Known limitations

- Two signed REST GETs every poll (`isOnline` + `state`) — no persistent connection, no
  adaptive fast/slow cadence for telemetry itself — simpler and fine for HA's coordinator
  model, but a driving session generates one data point per interval, not a continuous stream.
- Token is kept in memory only (not written to disk); a HA restart re-logs in from the
  stored email/password in the config entry.

## Security & privacy

Self-hosted, no server run by the author, no telemetry phoning home. Your CarLinko
email/password is stored only in HA's own config entry storage (encrypted at rest by HA
core) and sent only to CarLinko's own cloud (`*.hzhjcl.com`) over HTTPS/WSS to log in and
poll telemetry — exactly like the official app. No third-party backend, no analytics.

This is a hobby project with no warranty — see [LICENSE](LICENSE).
