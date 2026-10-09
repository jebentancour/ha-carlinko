# ha-carlinko

A native Home Assistant integration for cars connected to the **CarLinko** cloud — the
connected-car service behind the Jaecoo, Omoda and Chery apps (Jaecoo J5 EV, Omoda E5 and
other Chery-group vehicles).

It brings your car into Home Assistant as a single device with live telemetry (battery,
range, charging, doors, windows, tyres…) and remote controls (lock, A/C, windows, sunroof,
seat heating…), so you can build dashboards, get notifications and automate your car
alongside the rest of your home.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jebentancour&repository=ha-carlinko&category=integration)

## Features

- **UI setup** — no YAML. Log in with your CarLinko account, pick your region, and the car
  is detected automatically.
- **Adapts to your car** — the integration reads your vehicle's capabilities from CarLinko
  and only creates the entities your model actually supports. A BEV won't get fuel sensors;
  a car without a sunroof won't get a sunroof cover.
- **Telemetry**
  - Battery level, electric range, WLTP range, total range, odometer, speed, 12 V battery
  - Charging status, connector type (AC / DC), charging power, time remaining
  - Power, regen power and energy consumption
  - Fuel level, fuel consumption and engine RPM (on cars with an engine)
  - Doors, ignition, A/C compressor, windshield / steering wheel heating, air purifier
  - Tyre pressure and temperature for each wheel
  - Online / offline status of the car's connectivity module
  - Vehicle photos (front, side, top) from your CarLinko account
- **Remote controls**
  - Lock / unlock
  - Liftgate open / close
  - Sunroof open / close / tilt
  - Windows open / close / vent
  - A/C on / off, target temperature, Quick Heat and Quick Cool
  - Seat heating and ventilation (front and rear, off / low / medium / high)
  - Front defroster
  - Find Car (horn and lights) and Stop Charging
- **Translations** — English and Spanish.

## Requirements

- Home Assistant 2024.1 or newer
- A CarLinko account with your car paired to it
- Your car's connectivity module online (the same requirement as the official app)

## Installation

### HACS (recommended)

1. In HACS, open the menu → **Custom repositories**, add
   `https://github.com/jebentancour/ha-carlinko` with category **Integration** (or use the
   button above).
2. Search for **CarLinko** and install it.
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

## Using the controls

- Commands are sent the same way the official app sends them. CarLinko acknowledges that a
  command was delivered, and the integration refreshes the car's status right after, so
  entity states catch up within a few seconds.
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

- Cloud polling only: the integration doesn't receive pushed updates, so a drive is recorded
  as one data point per poll interval rather than a continuous stream.
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
