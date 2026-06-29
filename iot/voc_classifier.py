"""
iot/voc_classifier.py — VOC Sensor Array Plant Stress Classifier for AgriTwin
==============================================================================
Mengklasifikasikan jenis stres tanaman berdasarkan pembacaan array sensor VOC
(MQ-135, MQ-9, MQ-2) menggunakan LightGBM dengan fallback rule-based.

Kenapa VOC penting:
  Tanaman memancarkan Volatile Organic Compounds (VOC) spesifik saat mengalami
  stres — kekeringan, serangan hama, infeksi jamur, atau defisiensi nutrisi.
  Array sensor gas murah dapat mendeteksi perbedaan profil ini.

Hardware:
  MQ-135 → CO2, NH3, alkohol, benzena (metabolisme, stres protein)
  MQ-9   → CO, gas mudah terbakar (respirasi seluler, stres oksidatif)
  MQ-2   → LPG, propana, hidrogen, asap (VOC kompleks dari herbivori, dll.)

Setup:
  1. Latih model: python -m iot.voc_classifier --train
  2. Set VOC_MODEL_PATH di .env (opsional, default: iot/voc_model.pkl)
"""
import logging
import os
import pickle
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

STRESS_CLASSES: List[str] = [
    "healthy",
    "drought",
    "pest_attack",
    "fungal_infection",
    "nutrient_deficiency",
    "unknown",
]

_ACTIONS: Dict[str, str] = {
    "healthy":             "Kondisi normal — tidak perlu tindakan",
    "drought":             "Periksa kadar air tanah, tingkatkan frekuensi irigasi",
    "pest_attack":         "Periksa visual tanaman untuk tanda serangan hama, pertimbangkan pestisida hayati",
    "fungal_infection":    "Kurangi kelembapan, tingkatkan sirkulasi udara, isolasi tanaman terinfeksi",
    "nutrient_deficiency": "Periksa nilai EC dan pH larutan nutrisi, sesuaikan program pemupukan",
    "unknown":             "Pola VOC tidak dikenal — lakukan inspeksi manual",
}

_DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "voc_model.pkl")
_MODEL_PATH = os.environ.get("VOC_MODEL_PATH", _DEFAULT_MODEL_PATH)

# Minimum samples per class for training
_MIN_SAMPLES_PER_CLASS = 100


# ── Synthetic dataset ─────────────────────────────────────────────────────────

def generate_synthetic_dataset(n_per_class: int = 200) -> Tuple[List[List[float]], List[str]]:
    """Buat dataset sintetis untuk pelatihan awal.

    Profil VOC per kelas didasarkan pada literatur emisi biogenik tanaman
    (Peñuelas & Llusià, 2001; Holopainen & Gershenzon, 2010).
    Dataset lapangan nyata diharapkan menggantikan ini setelah pengumpulan field data.

    Args:
        n_per_class: Jumlah sampel per kelas stres.

    Returns:
        (X, y): Feature matrix dan label list.
    """
    try:
        import numpy as np
    except ImportError:
        logger.error("[VOC] numpy dibutuhkan untuk generate_synthetic_dataset")
        return [], []

    rng = np.random.default_rng(seed=42)
    X: List[List[float]] = []
    y: List[str] = []

    # Profile: (mq135_mean, mq135_std, mq9_mean, mq9_std, mq2_mean, mq2_std)
    profiles = {
        "healthy":             (250, 60,  140, 50,  160, 60),
        "drought":             (300, 70,  430, 90,  250, 70),
        "pest_attack":         (490, 100, 320, 80,  510, 110),
        "fungal_infection":    (690, 110, 240, 70,  340, 90),
        "nutrient_deficiency": (550, 100, 170, 60,  240, 70),
    }

    for stress_type, (m135, s135, m9, s9, m2, s2) in profiles.items():
        for _ in range(n_per_class):
            mq135 = float(np.clip(rng.normal(m135, s135), 0, 1000))
            mq9   = float(np.clip(rng.normal(m9,   s9),   0, 1000))
            mq2   = float(np.clip(rng.normal(m2,   s2),   0, 1000))
            X.append([mq135, mq9, mq2])
            y.append(stress_type)

    # "unknown": random combinations that don't fit any pattern
    n_unknown = n_per_class // 2
    for _ in range(n_unknown):
        X.append([
            float(rng.uniform(0, 1000)),
            float(rng.uniform(0, 1000)),
            float(rng.uniform(0, 1000)),
        ])
        y.append("unknown")

    logger.info("[VOC] Generated %d synthetic samples (%d classes)", len(y), len(set(y)))
    return X, y


# ── Classifier ────────────────────────────────────────────────────────────────

class VOCClassifier:
    """LightGBM classifier untuk deteksi stres tanaman dari sensor VOC.

    Fallback otomatis ke rule-based heuristics jika:
    - LightGBM tidak terinstal
    - Model belum dilatih
    - File model tidak ditemukan
    """

    def __init__(self, model_path: str = _MODEL_PATH):
        self.model_path   = model_path
        self._model       = None
        self._label_enc: Optional[Dict[str, int]] = None
        self._label_dec: Optional[Dict[int, str]] = None
        self._trained     = False
        self._load_attempted = False

    def _try_load_model(self) -> bool:
        """Coba load model dari disk. Return True jika berhasil."""
        if self._load_attempted:
            return self._trained
        self._load_attempted = True

        if not os.path.isfile(self.model_path):
            logger.info("[VOC] Model tidak ditemukan di %s — akan pakai rule-based", self.model_path)
            return False
        try:
            with open(self.model_path, "rb") as f:
                data = pickle.load(f)
            self._model     = data["model"]
            self._label_enc = data["label_enc"]
            self._label_dec = data["label_dec"]
            self._trained   = True
            logger.info("[VOC] Model loaded dari %s", self.model_path)
            return True
        except Exception as e:
            logger.warning("[VOC] Gagal load model: %s — fallback ke rule-based", e)
            return False

    def classify(self, readings: Dict[str, float]) -> Dict[str, Any]:
        """Klasifikasikan pembacaan sensor VOC ke jenis stres tanaman.

        Args:
            readings: dict dengan kunci mq135_value, mq9_value, mq2_value.
                      Nilai yang hilang default ke 0.0.

        Returns:
            dict: {
                "stress_type":        str,
                "confidence_score":   float (0.0–1.0),
                "recommended_action": str,
                "method":             "model" | "rule_based",
            }
        """
        mq135 = float(readings.get("mq135_value", 0.0))
        mq9   = float(readings.get("mq9_value",   0.0))
        mq2   = float(readings.get("mq2_value",   0.0))

        # Try LightGBM model first
        if self._try_load_model() and self._model is not None:
            try:
                import numpy as np
                features = np.array([[mq135, mq9, mq2]], dtype=float)
                proba    = self._model.predict_proba(features)[0]
                best_idx = int(proba.argmax())
                stress_type     = self._label_dec[best_idx]
                confidence_score = float(proba[best_idx])
                return {
                    "stress_type":        stress_type,
                    "confidence_score":   round(confidence_score, 4),
                    "recommended_action": _ACTIONS.get(stress_type, _ACTIONS["unknown"]),
                    "method":             "model",
                }
            except Exception as e:
                logger.warning("[VOC] Model prediction error: %s — fallback ke rule-based", e)

        # Rule-based fallback
        stress_type, confidence_score = self._rule_based_classify(mq135, mq9, mq2)
        return {
            "stress_type":        stress_type,
            "confidence_score":   round(confidence_score, 4),
            "recommended_action": _ACTIONS.get(stress_type, _ACTIONS["unknown"]),
            "method":             "rule_based",
        }

    def _rule_based_classify(self, mq135: float, mq9: float,
                              mq2: float) -> Tuple[str, float]:
        """Heuristik rule-based sebagai fallback saat model tidak tersedia.

        Ambang batas didasarkan pada profil emisi VOC biogenik tanaman.
        """
        # Fungal: high MQ135 (CO2 surge, ethanol-like compounds)
        if mq135 > 600:
            return "fungal_infection", 0.65

        # Nutrient deficiency: elevated MQ135 (NH3 from protein degradation), low MQ2
        if mq135 > 450 and mq2 < 400:
            return "nutrient_deficiency", 0.60

        # Pest attack: elevated MQ2 (complex terpene + green-leaf-volatile mix), elevated MQ9
        if mq2 > 480 and mq9 > 300:
            return "pest_attack", 0.62

        # Drought: elevated MQ9 (CO from oxidative stress), moderate MQ135
        if mq9 > 350 and mq135 < 420:
            return "drought", 0.60

        # Healthy: all parameters moderate to low
        if mq135 < 400 and mq9 < 250 and mq2 < 350:
            return "healthy", 0.75

        return "unknown", 0.40

    def train(
        self,
        X: List[List[float]],
        y: List[str],
        supplement_synthetic: bool = True,
    ) -> Dict[str, Any]:
        """Latih LightGBM classifier dari data sensor VOC.

        Args:
            X: Feature matrix [[mq135, mq9, mq2], ...]
            y: Label list ["healthy", "drought", ...]
            supplement_synthetic: Tambahkan synthetic data jika sampel per kelas < minimum.

        Returns:
            dict dengan metrics pelatihan dan path model tersimpan.
        """
        try:
            import lightgbm as lgb
            import numpy as np
        except ImportError as e:
            logger.error("[VOC] Dependency tidak tersedia untuk training: %s", e)
            return {"ok": False, "error": str(e), "method": "none"}

        # Supplement with synthetic if needed
        class_counts = {cls: y.count(cls) for cls in set(y)}
        if supplement_synthetic or any(
            class_counts.get(cls, 0) < _MIN_SAMPLES_PER_CLASS
            for cls in STRESS_CLASSES if cls != "unknown"
        ):
            logger.info("[VOC] Menambahkan data sintetis untuk melengkapi dataset")
            sx, sy = generate_synthetic_dataset(n_per_class=_MIN_SAMPLES_PER_CLASS)
            X = X + sx
            y = y + sy

        # Build label encoding
        unique_labels = sorted(set(y))
        label_enc     = {lbl: idx for idx, lbl in enumerate(unique_labels)}
        label_dec     = {idx: lbl for lbl, idx in label_enc.items()}

        X_arr = np.array(X, dtype=float)
        y_arr = np.array([label_enc[lbl] for lbl in y], dtype=int)

        # Train LightGBM
        clf = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=len(unique_labels),
            num_leaves=31,
            learning_rate=0.1,
            n_estimators=150,
            random_state=42,
            verbosity=-1,
        )
        clf.fit(X_arr, y_arr)

        # Persist model
        os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
        with open(self.model_path, "wb") as f:
            pickle.dump({"model": clf, "label_enc": label_enc, "label_dec": label_dec}, f)

        # Update in-memory state
        self._model       = clf
        self._label_enc   = label_enc
        self._label_dec   = label_dec
        self._trained     = True

        logger.info("[VOC] Model dilatih dengan %d sampel, disimpan ke %s", len(y), self.model_path)
        return {
            "ok":            True,
            "method":        "lightgbm",
            "samples_trained": len(y),
            "classes":       unique_labels,
            "model_saved":   self.model_path,
        }

    def train_from_scratch(self) -> Dict[str, Any]:
        """Latih model hanya dari dataset sintetis (tanpa data lapangan).

        Berguna untuk inisialisasi awal sebelum data ESP32 terkumpul.
        """
        X, y = generate_synthetic_dataset(n_per_class=_MIN_SAMPLES_PER_CLASS)
        if not X:
            return {"ok": False, "error": "Gagal generate synthetic dataset (numpy tidak tersedia?)"}
        return self.train(X, y, supplement_synthetic=False)

    def train_from_supabase(self) -> Dict[str, Any]:
        """Latih ulang model menggunakan data historis voc_readings dari Supabase.

        Strategi:
        - Ambil semua baris voc_readings dari Supabase (max 10.000)
        - Gunakan kolom (mq135_value, mq9_value, mq2_value, stress_type) sebagai dataset
        - Jika data kurang dari threshold, tambahkan synthetic data
        - Latih dan simpan model baru

        Returns:
            dict dengan metrics pelatihan.
        """
        X: List[List[float]] = []
        y: List[str] = []

        try:
            from db.supabase_client import get_voc_history
            rows = get_voc_history("", limit=10000)  # empty zone_id = semua zona
            for row in rows:
                stress_type = row.get("stress_type", "unknown")
                if stress_type not in STRESS_CLASSES:
                    continue
                X.append([
                    float(row.get("mq135_value", 0.0)),
                    float(row.get("mq9_value",   0.0)),
                    float(row.get("mq2_value",   0.0)),
                ])
                y.append(stress_type)
            logger.info("[VOC] Loaded %d baris dari Supabase untuk training", len(y))
        except Exception as e:
            logger.warning("[VOC] Gagal load data dari Supabase: %s — lanjut dengan synthetic", e)

        return self.train(X, y, supplement_synthetic=True)


# ── Public API ────────────────────────────────────────────────────────────────

def classify_voc(readings: Dict[str, float]) -> Dict[str, Any]:
    """Klasifikasikan pembacaan sensor VOC ke jenis stres tanaman.

    Fungsi utama yang dipanggil oleh mqtt_broker dan endpoint API.

    Args:
        readings: dict dengan kunci mq135_value, mq9_value, mq2_value.

    Returns:
        dict: {
            "stress_type": str,
            "confidence_score": float,
            "recommended_action": str,
            "method": "model" | "rule_based",
        }
    """
    return get_classifier().classify(readings)


# ── Singleton ─────────────────────────────────────────────────────────────────

_classifier: Optional[VOCClassifier] = None


def get_classifier() -> VOCClassifier:
    """Get atau create singleton VOCClassifier."""
    global _classifier
    if _classifier is None:
        _classifier = VOCClassifier()
    return _classifier


# ── CLI helper ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AgriTwin VOC Classifier")
    parser.add_argument("--train", action="store_true", help="Latih model dari dataset sintetis")
    parser.add_argument("--train-supabase", action="store_true", help="Latih ulang dari data Supabase")
    parser.add_argument("--classify", nargs=3, type=float, metavar=("MQ135", "MQ9", "MQ2"),
                        help="Klasifikasikan satu pembacaan")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    clf = get_classifier()

    if args.train:
        result = clf.train_from_scratch()
        print(result)
    elif args.train_supabase:
        result = clf.train_from_supabase()
        print(result)
    elif args.classify:
        mq135, mq9, mq2 = args.classify
        result = clf.classify({"mq135_value": mq135, "mq9_value": mq9, "mq2_value": mq2})
        print(result)
    else:
        parser.print_help()
