import paho.mqtt.client as mqtt
import json, time, math, random

print("[ARUNA] ESP32 Simulator starting...")
c = mqtt.Client()
c.connect("broker.emqx.io", 1883)
print("[MQTT] Connected to broker.emqx.io")

t = 0
while True:
    data = {
        "zone": "zone-B",
        "facility": "GH-INDO-01",
        "temp":  round(22 + math.sin(t)*2 + random.gauss(0,.2), 1),
        "rh":    round(72 + random.gauss(0,.5), 1),
        "humidity": round(72 + random.gauss(0,.5), 1),
        "co2":   int(850 + random.gauss(0,10)),
        "soil":  round(60 + random.gauss(0,.3), 1),
        "soil_moisture": round(60 + random.gauss(0,.3), 1),
        "ec":    round(1.9 + random.gauss(0,.02), 2),
        "ph":    round(6.4 + random.gauss(0,.01), 2),
        "ppfd":  int(400 + random.gauss(0,5)),
        "cold_temp": round(5 + random.gauss(0,.1), 1),
        "root_temp": round(20 + random.gauss(0,.2), 1),
        "flow":  round(1.3 + random.gauss(0,.1), 1),
        "pressure_bar": round(2.4 + random.gauss(0,.05), 2),
        "power_kw": round(1.85 + random.gauss(0,.1), 2),
        "relay_valve": 1,
        "led_pwm": 75,
        "fan_pwm": 50,
        "co2_inject": 0,
        "heater": 0,
        "pump": 1,
        "alarm": 0,
        "alarm_code": 0,
        "uptime_s": int(t*10)
    }

    topic = "greenhouse/GH-INDO-01/zone-B/sensor/all"
    c.publish(topic, json.dumps(data))

    print(f"T={data['temp']}°C  RH={data['rh']}%  CO2={data['co2']}ppm  soil={data['soil']}%  EC={data['ec']}  pH={data['ph']}")
    t += 0.1
    time.sleep(3)