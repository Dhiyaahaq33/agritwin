"""
alerts/alert_engine.py — Threshold Alert Engine for AgriTwin
=============================================================
Evaluasi parameter sensor terhadap threshold rules.
Kirim notifikasi via Telegram saat threshold dilanggar.
Simpan fired alerts ke Supabase.

VOC alert rules (dievaluasi via evaluate_voc()):
  HIGH_STRESS_DETECTED:    confidence > 0.80 dan stress_type != "healthy" → warning
  CRITICAL_STRESS_DETECTED: confidence > 0.90 dan stress_type in pest/fungal → critical
  UNKNOWN_VOC_PATTERN:     stress_type == "unknown" untuk 3 pembacaan berturut-turut → info
"""
import datetime
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_logger = logging.getLogger(__name__)

# ── Default thresholds per parameter ─────────────────────────────────────────

@dataclass
class AlertRule:
    param:     str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    severity:  str = "warning"    # info | warning | critical
    enabled:   bool = True
    cooldown_s: int = 300         # min seconds between repeated alerts


DEFAULT_RULES: List[AlertRule] = [
    # Temperature
    AlertRule("temperature", min_value=15.0, max_value=38.0, severity="warning"),
    AlertRule("temperature", min_value=10.0, max_value=42.0, severity="critical"),
    # Humidity
    AlertRule("humidity", min_value=30.0, max_value=95.0, severity="warning"),
    AlertRule("humidity", min_value=20.0, max_value=99.0, severity="critical"),
    # CO2
    AlertRule("co2", min_value=200, max_value=1200, severity="warning"),
    AlertRule("co2", max_value=2000, severity="critical"),
    # Soil moisture
    AlertRule("soil_moisture", min_value=20.0, max_value=90.0, severity="warning"),
    # pH
    AlertRule("ph", min_value=5.0, max_value=7.5, severity="warning"),
    # EC
    AlertRule("ec", min_value=0.5, max_value=4.0, severity="warning"),
]


class AlertEngine:
    """Evaluate sensor readings against threshold rules and fire alerts."""

    def __init__(self, rules: Optional[List[AlertRule]] = None):
        self.rules = rules or DEFAULT_RULES[:]
        self._last_fired: Dict[str, float] = {}  # "zone:param:severity" → timestamp
        self.fired_count = 0
        # Melacak jumlah pembacaan VOC "unknown" berturut-turut per zona
        self._voc_unknown_streak: Dict[str, int] = {}

    def evaluate(self, zone_id: str,
                 readings: Dict[str, float]) -> List[Dict]:
        """Evaluate readings against rules. Returns list of fired alerts.

        Each alert: {"zone_id", "param", "value", "severity", "message", "ts"}
        """
        alerts = []
        now = time.time()

        for rule in self.rules:
            if not rule.enabled or rule.param not in readings:
                continue

            value = readings[rule.param]
            violation = None

            if rule.min_value is not None and value < rule.min_value:
                violation = f"{rule.param} = {value:.1f} < min {rule.min_value:.1f}"
            elif rule.max_value is not None and value > rule.max_value:
                violation = f"{rule.param} = {value:.1f} > max {rule.max_value:.1f}"

            if not violation:
                continue

            # Cooldown check
            cooldown_key = f"{zone_id}:{rule.param}:{rule.severity}"
            last = self._last_fired.get(cooldown_key, 0)
            if now - last < rule.cooldown_s:
                continue

            self._last_fired[cooldown_key] = now
            self.fired_count += 1

            alert = {
                "zone_id":  zone_id,
                "param":    rule.param,
                "value":    value,
                "severity": rule.severity,
                "message":  f"[{rule.severity.upper()}] {violation}",
                "ts":       datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            alerts.append(alert)

            # Save ke Supabase (best-effort)
            try:
                from db.supabase_client import log_alert
                log_alert(zone_id, rule.severity, alert["message"],
                          param=rule.param, value=value)
            except Exception:
                pass

        # Send Telegram for warning/critical
        critical_alerts = [a for a in alerts if a["severity"] in ("warning", "critical")]
        if critical_alerts:
            _send_telegram_alerts(critical_alerts)

        return alerts

    def add_rule(self, rule: AlertRule):
        self.rules.append(rule)

    def get_rules(self) -> List[Dict]:
        return [{"param": r.param, "min": r.min_value, "max": r.max_value,
                 "severity": r.severity, "enabled": r.enabled} for r in self.rules]

    def evaluate_voc(self, zone_id: str, stress_type: str,
                     confidence_score: float) -> List[Dict]:
        """Evaluasi hasil klasifikasi VOC terhadap 3 VOC alert rules.

        Cooldown 300 detik digunakan untuk semua VOC rules (sama seperti sensor rules).
        Alerts dikirim ke Telegram dan disimpan ke Supabase.

        Args:
            zone_id:         ID zona yang mengirim data VOC.
            stress_type:     Hasil klasifikasi ("healthy", "drought", dll.).
            confidence_score: Skor kepercayaan model (0.0–1.0).

        Returns:
            List alert yang di-fire pada pemanggilan ini.
        """
        alerts = []
        now    = time.time()
        ts     = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # ── Update streak counter ───────────────────────────────────────────────
        if stress_type == "unknown":
            self._voc_unknown_streak[zone_id] = \
                self._voc_unknown_streak.get(zone_id, 0) + 1
        else:
            self._voc_unknown_streak[zone_id] = 0

        def _fire(rule_key: str, severity: str, message: str) -> Optional[Dict]:
            """Helper: cek cooldown dan buat alert dict jika belum cooldown."""
            cooldown_key = f"{zone_id}:VOC:{rule_key}:{severity}"
            if now - self._last_fired.get(cooldown_key, 0) < 300:
                return None
            self._last_fired[cooldown_key] = now
            self.fired_count += 1
            alert = {
                "zone_id":  zone_id,
                "param":    "voc",
                "value":    confidence_score,
                "severity": severity,
                "message":  f"[{severity.upper()}] {message}",
                "ts":       ts,
            }
            # Simpan ke Supabase (best-effort)
            try:
                from db.supabase_client import log_alert
                log_alert(zone_id, severity, alert["message"],
                          param="voc", value=confidence_score)
            except Exception as e:
                _logger.warning("[AlertEngine] Gagal simpan VOC alert: %s", e)
            return alert

        # ── Rule 1: HIGH_STRESS_DETECTED ────────────────────────────────────────
        # confidence > 0.80 dan tanaman TIDAK dalam kondisi sehat
        if confidence_score > 0.80 and stress_type != "healthy":
            alert = _fire(
                "HIGH_STRESS_DETECTED", "warning",
                f"Stres tanaman terdeteksi: {stress_type} "
                f"(confidence={confidence_score:.0%}) di zona {zone_id}",
            )
            if alert:
                alerts.append(alert)

        # ── Rule 2: CRITICAL_STRESS_DETECTED ────────────────────────────────────
        # confidence > 0.90 dan termasuk jenis stres kritis (hama atau jamur)
        _CRITICAL_TYPES = {"pest_attack", "fungal_infection"}
        if confidence_score > 0.90 and stress_type in _CRITICAL_TYPES:
            alert = _fire(
                "CRITICAL_STRESS_DETECTED", "critical",
                f"STRES KRITIS: {stress_type} dengan confidence {confidence_score:.0%} "
                f"di zona {zone_id} — tindakan segera diperlukan",
            )
            if alert:
                alerts.append(alert)

        # ── Rule 3: UNKNOWN_VOC_PATTERN ─────────────────────────────────────────
        # stress_type == "unknown" untuk 3 pembacaan berturut-turut
        if self._voc_unknown_streak.get(zone_id, 0) >= 3:
            alert = _fire(
                "UNKNOWN_VOC_PATTERN", "info",
                f"Pola VOC tidak dikenal selama 3 pembacaan berturut-turut "
                f"di zona {zone_id} — periksa sensor atau kondisi greenhouse",
            )
            if alert:
                alerts.append(alert)

        # Kirim Telegram untuk warning/critical
        notify = [a for a in alerts if a["severity"] in ("warning", "critical")]
        if notify:
            _send_telegram_alerts(notify)

        return alerts


# ── Telegram notification ────────────────────────────────────────────────────

def _send_telegram_alerts(alerts: List[Dict]):
    """Best-effort Telegram notification untuk alerts."""
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return

    try:
        import requests

        lines = ["🚨 *AgriTwin Alert*\n"]
        for a in alerts[:5]:  # max 5 per batch
            icon = "🔴" if a["severity"] == "critical" else "🟡"
            lines.append(f"{icon} `{a['zone_id']}` {a['message']}")
        lines.append(f"\n_🕐 {datetime.datetime.now().strftime('%H:%M:%S')}_")

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id":    chat_id,
                "text":       "\n".join(lines),
                "parse_mode": "Markdown",
            },
            timeout=5,
        )
    except Exception:
        pass


# ── Singleton ────────────────────────────────────────────────────────────────
_engine: Optional[AlertEngine] = None

def get_alert_engine() -> AlertEngine:
    global _engine
    if _engine is None:
        _engine = AlertEngine()
    return _engine
