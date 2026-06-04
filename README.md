# Smart Greenhouse Project

A microservice IoT platform for smart greenhouses.

## Structure

```text
config/       JSON configuration files
mqtt/         shared MQTT wrapper
catalog/      REST catalog and device registry
devices/      sensor and actuator connectors
control/      greenhouse controller
cloud/        ThingSpeak adaptor
dashboard/    simple web dashboard    
```

## Features

- Supports multiple greenhouses from `config/catalog.json`.
- Dashboard can register new greenhouses and add sensors/actuators.
- SensorConnector and ActuatorConnector periodically sync Catalog and can start newly added devices without restarting.
- Dashboard can switch the displayed greenhouse with a dropdown and `Refresh State`.
- Each greenhouse can have different plant type and thresholds in `config/catalog.json`.
- Sensor data is published as JSON over MQTT.
- Controller reads thresholds from Catalog and publishes commands to concrete actuator `device_id` targets.
- N/P/K fertilization uses separate pumps:
  - `nitrogen_pump (N)`
  - `phosphorus_pump (P)`
  - `potassium_pump (K)`

Internal actuator types remain `nitrogen_pump`, `phosphorus_pump`, and `potassium_pump`; the `(N/P/K)` suffix is a display label to avoid confusion.

## Note About Dashboard

The Dashboard is provided only as a demonstration and testing interface.  
The main focus of this project is the IoT backend architecture: Catalog, REST APIs, MQTT communication, SensorConnector, ActuatorConnector, Controller, and ThingSpeakAdaptor.

All core functions can be tested through REST requests and MQTT messages without using the Dashboard.

## Install

```powershell
pip install -r requirements.txt
```

## Run Order

Open separate terminals and run:

```powershell
python .\catalog\Catalog.py
python .\devices\ActuatorConnector.py
python .\control\Controller.py
python .\cloud\ThingSpeakAdaptor.py
python .\dashboard\Dashboard.py
python .\devices\SensorConnector.py
```

Minimal loop:

```powershell
python .\catalog\Catalog.py
python .\devices\ActuatorConnector.py
python .\control\Controller.py
python .\devices\SensorConnector.py
```

Dashboard:

```text
http://127.0.0.1:5000
```

## Dashboard Workflow

The main services read greenhouse and device data from Catalog.

Open Dashboard and use:

- `Add Greenhouse` to register a new greenhouse.
- `Change Greenhouse` and `Refresh State` to switch the displayed greenhouse.
- `Add Device To Selected Greenhouse` to add sensors or actuators to the currently loaded greenhouse.
- `Manual Override` to control a specific actuator by `device_id`.

Several device types receive numbered IDs, for example:

```text
GH1_soil_moist_0
GH1_soil_moist_1
GH1_grow_light_0
GH1_grow_light_1
```

Single device types do not use a number, for example:

```text
GH1_temperature
GH1_light
GH1_shade_cloth
```

## REST

- `GET /catalog`
- `GET /greenhouses`
- `POST /greenhouses`
- `POST /devices`
- `GET /sensors/<greenhouse_id>/latest`
- `GET /actuators/<greenhouse_id>/status`
- `POST /actuators/<greenhouse_id>/override`
- `GET /api/options`
- `GET /api/state?greenhouse_id=<greenhouse_id>`
- `POST /api/greenhouses`
- `POST /api/devices`
- `POST /api/override`

Manual override uses:

```text
Authorization: Bearer CHANGE_ME
```

## MQTT

Sensor topics:

```text
polito/iot/group8/greenhouse/<greenhouse_id>/sensors/...
```

Actuator command topics:

```text
polito/iot/group8/greenhouse/<greenhouse_id>/commands/<device_name>
```

## Notes

- ThingSpeak uses one channel/API key per greenhouse in `config/catalog.json`.
- Set `thingspeak.channels.GH1.api_key`, `thingspeak.channels.GH2.api_key`, etc. to upload each greenhouse to its own ThingSpeak Channel.
- Use placeholder ThingSpeak API keys before uploading the project to a public repository.
- All sensor payloads are JSON SenML-like messages.
- ThingSpeakAdaptor averages values by sensor type before uploading, so several soil moisture or fertility sensors share the same greenhouse-level field.
- Controller gets thresholds from Catalog, not hardcoded constants.
