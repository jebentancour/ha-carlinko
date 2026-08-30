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
| Liftgate | 4 | nonzero = open |
| Ignition | 5 | nonzero = on |
| Windows: front left / front right / rear left / rear right | 8, 2 bits each (0xC0/0x30/0x0C/0x03) | enum per window: 00=closed, 01=open, 10=vent, 11=open (fallback) |
| Sunroof | 9 | enum: 0x00=closed, 0x08=open, 0x0B=tilted (vent), else=open |
| 12 V battery (V) | 12–13 | uint16 × 0.01 |
| Speed (km/h) | 14–15 | uint16 ÷ 16 |
| Odometer (km) | 18–20 | uint24 |
| Fuel Level % *(only if `Engine` is set)* | 21 | raw |
| AC / climate on | 23 | nonzero = on |
| Climate Target Temperature (°C) | 24 | raw |
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
sentinels and charging-time invalid sentinels above, plus these diagnostic entities:

| Entity | Source | Meaning |
| --- | --- | --- |
| Control: A/C Min/Max Temperature (°C), Control: A/C Temperature Step | `A/C.SetTemperatureMin/Max`, `A/C.TemperatureStepValue` | the range/step the car's climate control accepts |
| Control: A/C / A/C Temperature / A/C Rapid Cool / A/C Rapid Heat / A/C Pre-condition Duration | `A/C.Switch/SetTemperature/RapidCool/RapidHeat/SetDuration` | whether this car model *supports* that remote-control feature — informational only, doesn't itself send a command |

The trip-schedule entities (from `terminalNoticeConfig`) were removed as unused. An earlier
`Control: Charging Power` diagnostic sensor was also removed as unused, but its underlying
check read the wrong `vehicleControlConfig` key (`chargingPower`, which never existed) instead
of the real `ChargingManagement` flag — see below, now fixed and used to gate the Stop
Charging button instead of a diagnostic sensor. `Control: Find Car` (`Search` flag) was
likewise removed as a diagnostic sensor and now gates the Find Car button below instead.
`Control: Scheduled Charging Supported` and `Control: Scheduled Trip Supported`
(`ScheduledCharging`/`ScheduledTravel` flags) were removed as unused — nothing in this
integration reads or writes vehicle schedules. `Control: Lock` (`Lock` flag),
`Control: Liftgate` (`PowerLiftgate` flag), `Control: Sunroof`/`Control: Sunroof Tilt`
(`Sunroof`/`SunroofTilting` flags) and `Control: Windows Open`/`Windows Close`/`Windows Vent`
(`WindowsOpen`/`WindowsClose`/`WindowsVent` flags), `Control: A/C Defog` (`A/C.Defogging`
flag) and `Control: Driver`/`Passenger Seat Ventilation`/`Heater`
(`A/C.DriverVent`/`AssistantVent`/`DriverHeater`/`AssistantHeater` flags) were likewise
removed as diagnostic sensors and now gate the `lock`/`cover`/`switch`/`fan` entities below
instead of the old read-only `Lock`, `Liftgate`, `Sunroof`, `Window *` and `Front Defroster`
binary_sensors and the `Seat Heating/Ventilation Left/Right` sensors.

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
