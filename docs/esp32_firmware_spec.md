# ESP32 Firmware Spec — AgriTwin IoT Integration

**Version:** 1.0 | **Date:** 31 May 2026

## MQTT Broker Connection

```
Host:     <your-cluster>.s1.eu.hivemq.cloud
Port:     8883 (TLS)
Username: (from HiveMQ Access Management)
Password: (from HiveMQ Access Management)
Protocol: MQTT v3.1.1
```

## Topic Structure

### ESP32 Publishes (sensor data → cloud)

| Topic | Payload | Interval |
|-------|---------|----------|
| `agritwin/{zone_id}/sensors/temperature` | `{"value": 25.3, "unit": "C"}` | 10s |
| `agritwin/{zone_id}/sensors/humidity` | `{"value": 72.5, "unit": "%"}` | 10s |
| `agritwin/{zone_id}/sensors/co2` | `{"value": 450, "unit": "ppm"}` | 30s |
| `agritwin/{zone_id}/sensors/soil_moisture` | `{"value": 65.0, "unit": "%"}` | 30s |
| `agritwin/{zone_id}/sensors/ph` | `{"value": 6.2, "unit": "pH"}` | 60s |
| `agritwin/{zone_id}/sensors/ec` | `{"value": 1.8, "unit": "mS/cm"}` | 60s |
| `agritwin/{zone_id}/sensors/light` | `{"value": 450, "unit": "umol"}` | 10s |
| `agritwin/{zone_id}/sensors/root_temp` | `{"value": 23.1, "unit": "C"}` | 30s |
| `agritwin/{zone_id}/flow` | `{"flow_lpm": 2.3, "target_lpm": 2.5, "pressure_bar": 1.2, "status": "normal"}` | 10s |

### ESP32 Subscribes (commands from cloud)

| Topic | Payload |
|-------|---------|
| `agritwin/{zone_id}/actuators` | `{"actuator": "valve", "value": 1.0, "ts": "2026-05-31T07:00:00Z"}` |
| `agritwin/{zone_id}/setpoints` | `{"temp_target": 26.0, "humidity_target": 70.0, "co2_target": 800}` |

## Payload Format

- **Encoding:** JSON UTF-8
- **Timestamp:** ISO 8601 UTC (e.g., `2026-05-31T07:00:00Z`)
- **QoS:** 1 (at least once delivery)
- **Zone ID format:** `ZONE-A`, `ZONE-B`, etc.

## Example: Arduino (PubSubClient + WiFiClientSecure)

```cpp
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const char* MQTT_HOST = "your-cluster.s1.eu.hivemq.cloud";
const int   MQTT_PORT = 8883;
const char* MQTT_USER = "esp32-zone-a";
const char* MQTT_PASS = "your_password";
const char* ZONE_ID   = "ZONE-A";

WiFiClientSecure espClient;
PubSubClient mqtt(espClient);

void publishSensor(const char* param, float value, const char* unit) {
    StaticJsonDocument<128> doc;
    doc["value"] = value;
    doc["unit"]  = unit;
    
    char topic[64], payload[128];
    snprintf(topic, sizeof(topic), "agritwin/%s/sensors/%s", ZONE_ID, param);
    serializeJson(doc, payload);
    mqtt.publish(topic, payload, true);
}

void setup() {
    WiFi.begin("SSID", "PASSWORD");
    espClient.setInsecure();  // or load CA cert
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.connect("esp32-zone-a", MQTT_USER, MQTT_PASS);
}

void loop() {
    mqtt.loop();
    publishSensor("temperature", readDHT(), "C");
    publishSensor("humidity",    readHumidity(), "%");
    publishSensor("soil_moisture", readSoilMoisture(), "%");
    delay(10000);
}
```

## Example: MicroPython (umqtt.simple)

```python
from umqtt.simple import MQTTClient
import ujson, ussl, time

ZONE_ID = "ZONE-A"
client = MQTTClient(
    "esp32-zone-a",
    "your-cluster.s1.eu.hivemq.cloud",
    port=8883, user="esp32-zone-a", password="your_password",
    ssl=True
)
client.connect()

def publish_sensor(param, value, unit=""):
    topic = f"agritwin/{ZONE_ID}/sensors/{param}"
    payload = ujson.dumps({"value": value, "unit": unit})
    client.publish(topic, payload)

while True:
    publish_sensor("temperature", read_dht(), "C")
    publish_sensor("humidity", read_humidity(), "%")
    time.sleep(10)
```
