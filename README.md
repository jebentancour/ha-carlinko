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
| Windows: front left / front right / rear left / rear right | 8, 2 bits each (0xC0/0x30/0x0C/0x03) | any bit set = open |
| Sunroof | 9 | nonzero = open |
| 12 V battery (V) | 12–13 | uint16 × 0.01 |
| Speed (km/h) | 14–15 | uint16 ÷ 16 |
| Odometer (km) | 18–20 | uint24 |
| Fuel Level % *(only if `Engine` is set)* | 21 | raw |
| AC / climate on | 23 | nonzero = on |
| Climate Target Temperature (°C) | 24 | raw |
| Battery Level % | 28 | raw |
| Battery Range (km) | 29–30 | uint16 |
| Seat Heating Left / Right | 32, 33 | enum: 0=off, 1=low, 2=medium, 3=high |
| Seat Ventilation Left / Right | 37, 38 | enum: 0=off, 1=low, 2=medium, 3=high |
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
| Control: Lock / Windows Open / Windows Close / Windows Vent / Sunroof / Sunroof Tilt / Liftgate / Find Car / Charging Management / Scheduled Charging Supported / Scheduled Trip Supported / Steering Wheel Heater / Front Windshield Heater / Charging Power / A/C / A/C Temperature / A/C Rapid Cool / A/C Rapid Heat / A/C Defog / A/C Air Purification / Driver\|Passenger Seat Ventilation / Driver\|Passenger\|Rear Seat Heater / A/C Fan High/Low Gear / A/C Pre-condition Duration | `Lock`, `WindowsOpen/Close/Vent`, `Sunroof`, `SunroofTilting`, `PowerLiftgate`, `Search`, `ChargingManagement`, `ScheduledCharging`, `ScheduledTravel`, `SteeringWheelHeater`, `FrontWindshieldHeater`, `chargingPower`, `A/C.Switch/SetTemperature/RapidCool/RapidHeat/Defogging/AirPurification/DriverVent/AssistantVent/DriverHeater/AssistantHeater/RearHeater/HighLowGear/SetDuration` | whether this car model *supports* that remote-control feature — informational only, this integration is read-only and doesn't send commands |

### Schedules & notifications

A separate account endpoint, `GET /user/device/manage/terminalNoticeConfig/{id}`, publishes
the trip/charge schedules and per-event push-notification preferences the official
app lets you configure. It's not part of the polled status blob (toggling these in the app
never moves a byte in it) and changes far less often than telemetry, so it's cached and
refetched on its own cadence rather than on every poll (default 5 minutes, configurable — see
[Options](#options)).

| Entity | Source | Meaning |
| --- | --- | --- |
| Trip Schedule: Enabled / Time / Days | `startupAppointment`, `extra` (JSON: `hour`/`minute`/`week`) | scheduled trip / pre-conditioning start |
| Charge Schedule: Enabled / Time / Duration / Days | `batterySchedule` (JSON: `enabled`/`hour`/`minute`/`duration`/`week`) | scheduled charging window |

## Options

Settings → Devices & services → CarLinko → Configure lets you change:

- **Poll interval** (default 120 s, minimum 30 s) — how often the telemetry blob (`isOnline` +
  `state`) is fetched.
- **Schedules/notifications refresh interval** (default 300 s, minimum 60 s) — how
  often `terminalNoticeConfig` (see [above](#schedules--notifications)) is refetched.
  It changes only when you edit those settings in the app, so it doesn't need to be as fresh
  as telemetry.

CarLinko's REST API has no documented rate limit, but stay reasonable.

## Known limitations

- Two signed REST GETs every poll (`isOnline` + `state`), plus `terminalNoticeConfig` on its
  own, slower cache (see [Options](#options)) — no persistent connection, no adaptive fast/slow
  cadence for telemetry itself — simpler and fine for HA's coordinator model, but a driving
  session generates one data point per interval, not a continuous stream.
- Token is kept in memory only (not written to disk); a HA restart re-logs in from the
  stored email/password in the config entry.

## Security & privacy

Self-hosted, no server run by the author, no telemetry phoning home. Your CarLinko
email/password is stored only in HA's own config entry storage (encrypted at rest by HA
core) and sent only to CarLinko's own cloud (`*.hzhjcl.com`) over HTTPS/WSS to log in and
poll telemetry — exactly like the official app. No third-party backend, no analytics.

This is a hobby project with no warranty — see [LICENSE](LICENSE).
