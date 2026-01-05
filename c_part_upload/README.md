# C Part – ThingSpeak Adaptor + User Awareness

## What I implemented
- **ThingSpeak adaptor**: subscribes to sensor MQTT topic and uploads (or mock-uploads) data to ThingSpeak every N seconds.
- **User awareness**: provides a simple dashboard/API that reads latest sensor data and actuator status via REST, and supports manual override.

## How to run
1. Install dependencies:
   ```bash
   pip install flask requests paho-mqtt
