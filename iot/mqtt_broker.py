"""
iot/mqtt_broker.py — HiveMQ Cloud MQTT Broker for AgriTwin
===========================================================
Menghubungkan ESP32 hardware ke cloud via MQTT TLS (port 8883).

Setup (5 menit, gratis):
  1. Buka https://www.hivemq.com/mqtt-cloud-broker/ → Create Free Cluster
  2. Buat credential (username + password) di tab Access Management
  3. Isi di .env: HIVEMQ_HOST, HIVEMQ_USERNAME, HIVEMQ_PASSWORD

Topics:
  agritwin/{zone_id}/sensors/+  → sensor data dari ESP32
  agritwin/{zone_id}/flow       → flow meter data
  agritwin/{zone_id}/actuators  → commands ke ESP32
  agritwin/{zone_id}/setpoints  → target values
  agritwin/{zone_id}/voc/+      → VOC sensor array (MQ-135, MQ-9, MQ-2)
"""
import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Callable, Dict, List, Optional

_logger = logging.getLogger(__name__)

# ── Config dari .env ─────────────────────────────────────────────────────────
_HIVEMQ_HOST     = os.environ.get("HIVEMQ_HOST", "")
_HIVEMQ_PORT     = int(os.environ.get("HIVEMQ_PORT", "8883"))
_HIVEMQ_USERNAME = os.environ.get("HIVEMQ_USERNAME", "")
_HIVEMQ_PASSWORD = os.environ.get("HIVEMQ_PASSWORD", "")


class MQTTBroker:
    """Managed MQTT client untuk HiveMQ Cloud.

    Jika HiveMQ tidak dikonfigurasi, fallback ke in-memory simulator
    (identik dengan MQTTSimulator di tumbal.py).
    """

    def __init__(self, host: str = "", port: int = 8883,
                 username: str = "", password: str = "",
                 client_id: str = ""):
        self.host     = host or _HIVEMQ_HOST
        self.port     = port if host else _HIVEMQ_PORT
        self.username = username or _HIVEMQ_USERNAME
        self.password = password or _HIVEMQ_PASSWORD
        self.client_id = client_id or f"agritwin-{int(time.time())}"

        self._client    = None
        self._connected = False
        self._error     = ""
        self._lock      = threading.Lock()

        # Message bus (in-memory, untuk simulator mode juga)
        self.message_bus: deque = deque(maxlen=1000)
        self.subscriptions: Dict[str, List[Callable]] = defaultdict(list)
        self.msg_count = 0

        # VOC reading buffer: zone_id → {mq135_value, mq9_value, mq2_value}
        # Diupdate setiap kali satu sensor VOC baru masuk, lalu klasifikasi dijalankan
        self._voc_buffer: Dict[str, Dict[str, float]] = defaultdict(dict)

        # Mode detection
        self.is_cloud = bool(self.host and self.username)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def mode(self) -> str:
        if self._connected:
            return "cloud"
        if self.is_cloud:
            return "disconnected"
        return "simulator"

    def connect(self) -> bool:
        """Connect ke HiveMQ Cloud. Returns True jika berhasil."""
        if not self.is_cloud:
            self._connected = False
            return False

        try:
            import paho.mqtt.client as mqtt

            self._client = mqtt.Client(
                client_id=self.client_id,
                protocol=mqtt.MQTTv311,
            )
            self._client.username_pw_set(self.username, self.password)
            self._client.tls_set()  # TLS for port 8883

            def _on_connect(client, userdata, flags, rc):
                if rc == 0:
                    self._connected = True
                    self._error = ""
                    # Re-subscribe semua topic
                    for topic in list(self.subscriptions.keys()):
                        client.subscribe(topic, qos=1)
                else:
                    self._connected = False
                    self._error = f"Connect failed rc={rc}"

            def _on_disconnect(client, userdata, rc):
                self._connected = False
                if rc != 0:
                    self._error = f"Unexpected disconnect rc={rc}"
                    # paho-mqtt loop_start handles automatic reconnect

            def _on_message(client, userdata, msg):
                try:
                    payload = json.loads(msg.payload.decode())
                except Exception:
                    payload = {"raw": msg.payload.decode("utf-8", errors="replace")}

                self.message_bus.append({
                    "topic":   msg.topic,
                    "payload": payload,
                    "ts":      time.time(),
                    "qos":     msg.qos,
                })
                self.msg_count += 1

                # Call subscribers
                for pattern, callbacks in self.subscriptions.items():
                    if self._topic_match(pattern, msg.topic):
                        for cb in callbacks:
                            try:
                                cb(msg.topic, payload)
                            except Exception:
                                pass

                # Auto-ingest ke Supabase
                self._auto_ingest(msg.topic, payload)

            self._client.on_connect    = _on_connect
            self._client.on_disconnect = _on_disconnect
            self._client.on_message    = _on_message

            self._client.reconnect_delay_set(min_delay=1, max_delay=30)
            self._client.connect_async(self.host, self.port, keepalive=60)
            self._client.loop_start()

            # Wait for connection (max 5 sec)
            for _ in range(50):
                if self._connected:
                    return True
                time.sleep(0.1)

            return self._connected

        except ImportError:
            self._error = "paho-mqtt not installed"
            return False
        except Exception as e:
            self._error = str(e)[:100]
            return False

    def disconnect(self):
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
        self._connected = False

    def subscribe(self, topic: str, callback: Optional[Callable] = None):
        """Subscribe ke MQTT topic. Callback: fn(topic, payload_dict)."""
        if callback:
            self.subscriptions[topic].append(callback)
        if self._client and self._connected:
            self._client.subscribe(topic, qos=1)

    def publish(self, topic: str, payload: dict, qos: int = 1) -> bool:
        """Publish message ke MQTT topic."""
        if self._client and self._connected:
            try:
                msg = json.dumps(payload)
                result = self._client.publish(topic, msg, qos=qos)
                return result.rc == 0
            except Exception:
                return False

        # Simulator mode: langsung masuk ke message_bus
        self.message_bus.append({
            "topic": topic, "payload": payload,
            "ts": time.time(), "qos": qos,
        })
        self.msg_count += 1
        # Trigger subscribers
        for pattern, callbacks in self.subscriptions.items():
            if self._topic_match(pattern, topic):
                for cb in callbacks:
                    try:
                        cb(topic, payload)
                    except Exception:
                        pass
        return True

    def publish_setpoints(self, zone_id: str, setpoints: dict):
        """Kirim target setpoints ke ESP32."""
        return self.publish(f"agritwin/{zone_id}/setpoints", setpoints)

    def publish_actuator(self, zone_id: str, actuator: str, value: float):
        """Kirim perintah aktuator ke ESP32."""
        return self.publish(f"agritwin/{zone_id}/actuators", {
            "actuator": actuator, "value": value,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def get_recent_messages(self, topic_filter: str = "",
                            limit: int = 50) -> List[dict]:
        """Ambil pesan terbaru dari message bus."""
        msgs = list(self.message_bus)
        if topic_filter:
            msgs = [m for m in msgs if topic_filter in m["topic"]]
        return msgs[-limit:]

    def status_dict(self) -> dict:
        return {
            "mode":      self.mode,
            "connected": self._connected,
            "host":      self.host or "(simulator)",
            "messages":  self.msg_count,
            "error":     self._error,
        }

    # ── Internal ─────────────────────────────────────────────────────────────

    def _auto_ingest(self, topic: str, payload: dict):
        """Auto-ingest sensor data ke Supabase saat terima dari ESP32."""
        # Topic format: agritwin/{zone_id}/sensors/{param}
        parts = topic.split("/")
        if len(parts) >= 4 and parts[2] == "sensors":
            zone_id = parts[1]
            param   = parts[3]
            value   = payload.get("value", payload.get("v"))
            if value is not None:
                try:
                    from db.supabase_client import log_sensor
                    log_sensor(zone_id, {param: float(value)}, source="sensor")
                except Exception:
                    pass

        # Flow meter: agritwin/{zone_id}/flow
        elif len(parts) >= 3 and parts[2] == "flow":
            zone_id = parts[1]
            try:
                from db.supabase_client import log_flow
                log_flow(
                    zone_id,
                    float(payload.get("flow_lpm", 0)),
                    float(payload.get("target_lpm", 0)),
                    float(payload.get("pressure_bar", 0)),
                    payload.get("status", "normal"),
                )
            except Exception:
                pass

        # VOC sensor array: agritwin/{zone_id}/voc/{sensor_type}
        # sensor_type: mq135, mq9, mq2
        elif len(parts) >= 4 and parts[2] == "voc":
            zone_id     = parts[1]
            sensor_type = parts[3]   # mq135 | mq9 | mq2
            value       = payload.get("value", payload.get("v"))
            if value is not None:
                self._ingest_voc(zone_id, sensor_type, float(value), payload)

    def _ingest_voc(self, zone_id: str, sensor_type: str,
                    value: float, raw_payload: dict):
        """Buffer satu pembacaan VOC dan jalankan klasifikasi stres tanaman.

        Setiap kali satu dari tiga sensor (mq135, mq9, mq2) mengirim data,
        buffer per zona diupdate dan klasifikasi dijalankan menggunakan nilai
        terbaru yang tersedia (nilai sensor yang belum menerima data = 0.0).

        Hasil klasifikasi disimpan ke Supabase voc_readings dan dievaluasi
        terhadap VOC alert rules.
        """
        # Normalize sensor key: "mq135" → "mq135_value", dll.
        key = f"{sensor_type}_value" if not sensor_type.endswith("_value") else sensor_type

        with self._lock:
            self._voc_buffer[zone_id][key] = value
            current_readings = dict(self._voc_buffer[zone_id])

        try:
            from iot.voc_classifier import classify_voc
            result = classify_voc(current_readings)
        except Exception as e:
            _logger.error("[MQTT] VOC classification error di zone %s: %s", zone_id, e)
            return

        mq135 = current_readings.get("mq135_value", 0.0)
        mq9   = current_readings.get("mq9_value",   0.0)
        mq2   = current_readings.get("mq2_value",   0.0)

        # Persist ke Supabase
        try:
            from db.supabase_client import log_voc_reading
            log_voc_reading(
                zone_id=zone_id,
                mq135_value=mq135,
                mq9_value=mq9,
                mq2_value=mq2,
                stress_type=result["stress_type"],
                confidence_score=result["confidence_score"],
                recommended_action=result["recommended_action"],
                raw_payload=raw_payload,
            )
        except Exception as e:
            _logger.error("[MQTT] VOC Supabase ingest error di zone %s: %s", zone_id, e)

        # Evaluasi VOC alert rules
        try:
            from alerts.alert_engine import get_alert_engine
            get_alert_engine().evaluate_voc(
                zone_id=zone_id,
                stress_type=result["stress_type"],
                confidence_score=result["confidence_score"],
            )
        except Exception as e:
            _logger.error("[MQTT] VOC alert evaluation error di zone %s: %s", zone_id, e)

    @staticmethod
    def _topic_match(pattern: str, topic: str) -> bool:
        """Simple MQTT topic matching (+, #)."""
        p_parts = pattern.split("/")
        t_parts = topic.split("/")
        for i, pp in enumerate(p_parts):
            if pp == "#":
                return True
            if i >= len(t_parts):
                return False
            if pp == "+":
                continue
            if pp != t_parts[i]:
                return False
        return len(p_parts) == len(t_parts)


# ── Singleton ────────────────────────────────────────────────────────────────
_broker: Optional[MQTTBroker] = None

def get_broker() -> MQTTBroker:
    """Get atau create singleton MQTT broker."""
    global _broker
    if _broker is None:
        _broker = MQTTBroker()
        # Subscribe ke topik sensor dan VOC agar _auto_ingest menerima pesan dari ESP32
        _broker.subscribe("agritwin/+/sensors/+")
        _broker.subscribe("agritwin/+/flow")
        _broker.subscribe("agritwin/+/voc/+")   # VOC sensor array (MQ-135, MQ-9, MQ-2)
        if _broker.is_cloud:
            _broker.connect()
    return _broker
