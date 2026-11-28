# ha-carlinko

A native Home Assistant integration for cars connected to the **CarLinko** cloud — the
connected-car service behind the Jaecoo, Omoda and Chery apps (Jaecoo J5 EV, Omoda E5 and
other Chery-group vehicles).

It brings your car into Home Assistant as a single device with live telemetry (battery,
range, charging, doors, windows, tyres…) and remote controls (lock, A/C, windows, sunroof,
seat heating…), so you can build dashboards, get notifications and automate your car
alongside the rest of your home.

[![Open your Home Assistant instance and open this repository in the Marketplace (HACS).](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jebentancour&repository=ha-carlinko&category=integration)

## Features

- **UI setup** — no YAML. Log in with your CarLinko account, pick your region, and the car
  is detected automatically.
- **Adapts to your car** — the integration reads your vehicle's capabilities from CarLinko
  and only creates the entities your model actually supports. A BEV won't get fuel sensors;
  a car without a sunroof won't get a sunroof cover.
- **Telemetry**
  - Battery level, electric range, WLTP range, total range, odometer, speed, 12V battery
  - Charging status, connector type (AC / DC), charging power, time remaining
  - Power, regen power and energy consumption
  - Fuel level, fuel consumption and engine RPM (on cars with an engine)
  - Doors, ignition, A/C compressor
  - Tyre pressure and temperature for each wheel
  - Online / offline status of the car's connectivity module, and its firmware version
  - Vehicle photos (front, side, top) from your CarLinko account
  - Data source (cloud / Bluetooth) and an "at home" presence sensor when Bluetooth is enabled
- **Remote controls**
  - Lock / unlock
  - Liftgate open / close
  - Sunroof open / close / tilt
  - Roof sunshade open / close
  - Windows open / close / vent
  - A/C on / off, target temperature, Quick Heat and Quick Cool
  - Seat heating and ventilation (front and rear, off / low / medium / high)
  - Front and rear defroster
  - Windshield heating, steering wheel heating and air purifier
  - Find Vehicle (horn and lights) and Stop Charging
- **Local Bluetooth (optional)** — when the car is in range of a Home Assistant Bluetooth
  adapter, commands and telemetry can go directly to the car over BLE: either alongside the
  cloud (Bluetooth in range, cloud when out of range) or Bluetooth-only for when the cloud
  account isn't available. See [Bluetooth](#bluetooth-local-control--telemetry).
- **Clear feedback** — when the car refuses a command, Home Assistant tells you why (a door
  is open, the vehicle is on…).
- **Translations** — English and Spanish, including entity names and error messages.

## Requirements

- Home Assistant 2024.1 or newer (on 2026.11+ the Marketplace, formerly HACS, is built in)
- A CarLinko account with your car paired to it
- Your car's connectivity module online (the same requirement as the official app)

## Installation

### Marketplace / HACS (recommended)

Starting with Home Assistant **2026.11**, HACS is built into Home Assistant as the
**Marketplace** (**Settings → Marketplace**). On earlier versions, install HACS first and
use it the same way — the steps below only differ in where you find the menu.

1. Click the button above, or add this repository by hand:
   - **Home Assistant 2026.11+:** go to **Settings → Marketplace → Add from link** (top
     right), enter `jebentancour/ha-carlinko`, and select **Add**. Choose type
     **Integration** if asked.
   - **HACS (older versions):** open the HACS menu → **Custom repositories**, add
     `https://github.com/jebentancour/ha-carlinko` with category **Integration**.
2. Open the **CarLinko** entry and select **Install**.
3. Restart Home Assistant.

### Manual

1. Copy `custom_components/carlinko/` into the `custom_components/` folder of your Home
   Assistant configuration directory.
2. Restart Home Assistant.

## Setup

1. Go to **Settings → Devices & services → Add integration** and search for **CarLinko**.
2. Enter your CarLinko email and password, and choose the **region** your account was
   created in (e.g. South America, Europe/Middle East/Africa, Southeast Asia…).
3. If your account has more than one car, pick the one to add. Repeat the flow to add more
   cars.

> **Tip: use a second account.** CarLinko allows only one active session per account, so
> logging in from Home Assistant can sign you out of the official app. Share the car with a
> second CarLinko account from the official app and use that one in Home Assistant.

If you see *"No CarLinko account with that email in this region"*, your account lives in a
different region — try another one from the list.

## Options

**Settings → Devices & services → CarLinko → Configure**

- **Poll interval** — how often the car's status is refreshed. Default 120 s, minimum 30 s.
  CarLinko doesn't publish a rate limit, so keep it reasonable.
- **Transport** — how commands and telemetry travel:
  - **Cloud only** (default) — always use the CarLinko cloud.
  - **Bluetooth and cloud** — use Bluetooth when the car is in range of a Home Assistant
    Bluetooth adapter, and fall back to the cloud when the car is out of range.
  - **Bluetooth only** — use only Bluetooth, never the cloud (for when the cloud account isn't
    available). Commands and telemetry need the car in BLE range.

## Bluetooth (local control & telemetry)

When the car is near a Home Assistant Bluetooth adapter, the integration can talk to the car's
T-box directly over Bluetooth Low Energy. This is handy when the cloud link is unreliable or
absent.

- **Enable it** in **Configure → Transport** (see above). No extra setup: the car is found by
  its advertised name, and the details needed for local control are fetched automatically.
- **Commands** use BLE when the car is in range; in *Bluetooth and cloud* they fall back to the
  cloud when it isn't, while *Bluetooth only* has no cloud fallback.
- **Telemetry** is read from whichever source is available; the sensors never jump backwards.
  Because the odometer only ever increases, it's used as a simple freshness clock — a reading
  is accepted only if its odometer is at least the last one seen. So a stale cloud reply (for
  example after you drive out of Bluetooth range) is ignored instead of snapping the battery
  and other sensors back to an old value.
- **Entities:** a *Data Source* diagnostic sensor shows whether the current state came from the
  cloud or Bluetooth, and an *At Home* presence sensor turns on while the car is in BLE range.
- **Requirements:** a working Bluetooth adapter or ESPHome Bluetooth proxy within range of
  where the car is parked, and the Home Assistant **Bluetooth** integration set up.

## Using the controls

- After each command the integration refreshes the car's status, so entity states catch up
  within a few seconds. If the car refuses a command, you get an error with the reason.
- **Windows:** the car only supports opening, closing or venting all windows at once. There's
  one entity per window so each can show its own state, but controlling any of them moves
  all four.
- **A/C:** the `climate` entity offers *Off*, *Auto*, and — where the car supports them —
  *Heat* and *Cool*, which trigger Quick Heat and Quick Cool. Target temperature follows the
  range and step size of your model.
- When the car goes offline (e.g. parked without signal), entities keep their last known
  values instead of becoming unavailable.

### Automation ideas

- Notify when charging completes or is interrupted (`Charging Status`).
- Alert if the car is left unlocked or with a window open at night.
- Pre-condition the cabin with the A/C before your morning commute.
- Stop charging automatically when the battery reaches a target level.
- Feed the charging power into the Energy dashboard.

## Known limitations

- Polling, not streaming: whether over the cloud or Bluetooth, the car is read once per poll
  interval, so a drive is recorded as one data point per interval rather than a continuous stream.
- Bluetooth needs the car in range of a Home Assistant Bluetooth adapter or proxy, and the car
  accepts a single BLE client at a time — if the official app is connected, Home Assistant waits.
- There's no per-window control (see above).
- Only one active session per CarLinko account (see the setup tip).

## Security & privacy

Your credentials are stored only in Home Assistant's own config entry storage and are sent
only to CarLinko's servers over HTTPS — exactly like the official app. There is no
third-party backend, no analytics and no telemetry sent anywhere else. Use this integration
only with your own account and car.

## AI disclaimer

This integration was written largely with the help of AI coding tools, under my supervision
and with testing on my own car. Every feature my car supports is checked against it before
it ships; the rest follow the same patterns but rely on owners of other models to confirm
them. CarLinko cars come in many models and regions, and I can only test the ones I have
access to.

If something doesn't work as expected on your car — or works great — please
[open an issue](https://github.com/jebentancour/ha-carlinko/issues) and share your
experience, including your model and region. Feedback from other owners is what makes the
integration better for everyone.

## Credits

Developed alongside
[j5-ev-dashboard](https://github.com/GodrezJr2/j5-ev-dashboard), a standalone dashboard for
the same cars.

This is an unofficial hobby project, not affiliated with CarLinko, Chery, Jaecoo or Omoda,
and comes with no warranty — see [LICENSE](LICENSE).
