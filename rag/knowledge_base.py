"""
rag/knowledge_base.py — RAG Knowledge Base for AgriTwin
========================================================
Hybrid retrieval strategy:
  1. Vector search: Gemini text-embedding-004 + cosine similarity (in-memory cache)
  2. DB persistence: Supabase pgvector (when extension enabled — see setup_supabase.sql)
  3. Keyword fallback: TF-style word matching (no API key required)

Setup pgvector (opsional, untuk persistence embedding di DB):
  1. Buka Supabase SQL Editor
  2. Jalankan: CREATE EXTENSION IF NOT EXISTS vector;
  3. Jalankan ALTER TABLE dari setup_supabase.sql (bagian pgvector)
  4. Panggil seed_knowledge() sekali untuk embed dan simpan dokumen
"""
import math
import os
from typing import Dict, List, Optional, Tuple

# ── Seed documents: panduan agronomi Indonesia ──────────────────────────────

SEED_DOCUMENTS: List[Dict] = [
    {
        "title": "Budidaya Tomat Greenhouse",
        "source": "Balitsa Lembang",
        "content": (
            "Tomat optimal pada suhu 22-28°C siang, 15-20°C malam. "
            "Kelembapan ideal 60-80%. pH tanah 6.0-6.8. EC 2.0-3.5 mS/cm. "
            "Kebutuhan air 4-6 L/tanaman/hari saat berbuah. "
            "Pemupukan: NPK 16-16-16 dosis 200 kg/ha, ditambah kalsium boron "
            "saat pembentukan buah. Jarak tanam 50x60 cm. "
            "Panen mulai 60-70 HST. Potensi hasil 60-80 ton/ha/tahun. "
            "Hama utama: kutu kebul (Bemisia tabaci), lalat buah, ulat buah. "
            "Penyakit utama: layu fusarium, busuk daun Phytophthora, virus TYLCV."
        ),
    },
    {
        "title": "Budidaya Selada Hidroponik",
        "source": "Badan Litbang Pertanian",
        "content": (
            "Selada tumbuh optimal pada suhu 15-25°C. pH larutan nutrisi 5.5-6.5. "
            "EC 1.0-1.5 mS/cm untuk selada daun, 1.5-2.0 untuk selada kepala. "
            "PPFD optimal 200-400 umol/m2/s, fotoperiode 14-16 jam. "
            "Sistem NFT atau DFT dengan debit 1-2 L/menit. "
            "Panen 25-35 HST. Hasil 15-20 kepala/m2. "
            "Masalah umum: tip burn (defisiensi kalsium), busuk akar Pythium, "
            "aphid, dan alga pada sistem terbuka."
        ),
    },
    {
        "title": "Budidaya Cabai dalam Greenhouse",
        "source": "BPTP Jawa Barat",
        "content": (
            "Cabai merah optimal pada suhu 24-30°C, kelembapan 60-70%. "
            "pH tanah 6.0-7.0. Kebutuhan air 3-5 L/tanaman/hari. "
            "Pemupukan: N 200 kg/ha, P2O5 150 kg/ha, K2O 200 kg/ha. "
            "Jarak tanam 50x70 cm. Panen mulai 75-85 HST, bisa sampai 20 kali panen. "
            "Potensi hasil 15-25 ton/ha. Harga fluktuatif Rp 25.000-80.000/kg. "
            "Hama: thrips, kutu daun, tungau. Penyakit: antraknosa, layu bakteri, "
            "busuk buah, virus CMV dan gemini virus."
        ),
    },
    {
        "title": "Identifikasi Penyakit Tanaman Umum",
        "source": "Puslitbang Hortikultura",
        "content": (
            "Layu Fusarium: daun menguning dari bawah, pembuluh coklat. "
            "Pengendalian: varietas tahan, rotasi tanaman, Trichoderma. "
            "Busuk Daun (Phytophthora): bercak basah kehijauan, menyebar cepat saat hujan. "
            "Pengendalian: fungisida Mancozeb 2g/L, drainase baik. "
            "Antraknosa: bercak bulat cekung pada buah. Pengendalian: fungisida, "
            "sanitasi, hindari panen saat hujan. "
            "Virus TYLCV: daun menggulung ke atas, kerdil. Vektor: kutu kebul. "
            "Pengendalian: mulsa perak, insektisida, varietas tahan. "
            "Busuk Akar Pythium: akar coklat lembek, tanaman layu. "
            "Pengendalian: sterilisasi media, H2O2 50 ppm, Trichoderma."
        ),
    },
    {
        "title": "Pemupukan Berimbang Hortikultura",
        "source": "Kementan RI",
        "content": (
            "Prinsip pemupukan 4T: Tepat jenis, dosis, waktu, cara. "
            "Nitrogen (N): pertumbuhan vegetatif, daun hijau. Defisiensi: daun pucat. "
            "Fosfor (P): perakaran dan pembungaan. Defisiensi: daun ungu kemerahan. "
            "Kalium (K): kualitas buah dan ketahanan penyakit. Defisiensi: tepi daun coklat. "
            "Kalsium (Ca): struktur sel, cegah tip burn. Sumber: kapur dolomit, kalsium nitrat. "
            "Magnesium (Mg): klorofil. Defisiensi: klorosis antar tulang daun tua. "
            "Pupuk organik: kompos 10-20 ton/ha sebagai pembenah tanah. "
            "Pupuk hayati: Trichoderma, mikoriza, PGPR untuk biostimulasi."
        ),
    },
    {
        "title": "Pengelolaan Iklim Greenhouse Indonesia",
        "source": "IPB University",
        "content": (
            "Indonesia tropis: suhu rata-rata 26-32°C, kelembapan 70-90%. "
            "Greenhouse harus mampu menurunkan suhu 3-5°C dari luar. "
            "Ventilasi natural: bukaan atap 15-25% luas lantai. "
            "Exhaust fan: kecepatan udara 0.5-1.0 m/s di kanopi tanaman. "
            "Fogging/misting: menurunkan suhu 2-4°C, naikkan RH 10-15%. "
            "Shading net: 30-50% untuk dataran rendah, 20-30% dataran tinggi. "
            "CO2 enrichment: 800-1200 ppm saat ventilasi tertutup. "
            "LED supplemental: 100-200 umol/m2/s untuk musim hujan. "
            "Monitoring: sensor suhu/RH tiap 10 detik, CO2 tiap 30 detik."
        ),
    },
    {
        "title": "Irigasi Presisi dan Fertigasi",
        "source": "FAO Indonesia",
        "content": (
            "Evapotranspirasi (ET) dihitung dengan Penman-Monteith FAO-56. "
            "Koefisien tanaman (Kc): tomat 0.6-1.15, cabai 0.6-1.05, selada 0.7-1.0. "
            "Soil moisture optimal: 60-80% kapasitas lapang. "
            "Drip irrigation: efisiensi 90-95%, debit 2-4 L/jam per emitter. "
            "Fertigasi: NPK terlarut via drip, 2-3 kali/hari saat generatif. "
            "Kualitas air: EC < 0.5 mS/cm, pH 6.5-7.0. "
            "Sensor soil moisture: TDR atau kapasitif, kedalaman 15-20 cm. "
            "Deficit irrigation: kurangi 20-30% saat ripening untuk tingkatkan Brix."
        ),
    },
    {
        "title": "Hama dan Pengendalian Hayati",
        "source": "Balai Besar Peramalan OPT",
        "content": (
            "IPM (Integrated Pest Management) prioritas: "
            "1. Kultur teknis: sanitasi, rotasi, varietas tahan. "
            "2. Mekanis: perangkap kuning, perangkap feromon. "
            "3. Hayati: Beauveria bassiana untuk kutu kebul, "
            "Trichoderma harzianum untuk patogen tanah, "
            "Bacillus thuringiensis untuk ulat. "
            "4. Kimia: pestisida selektif sebagai pilihan terakhir. "
            "Thrips: perangkap biru, Spinosad 0.5 mL/L. "
            "Kutu daun: Imidacloprid 0.5 mL/L atau Beauveria. "
            "Tungau: Abamectin 0.5 mL/L, jaga kelembapan >70%."
        ),
    },
    {
        "title": "Kalender Tanam Hortikultura Jawa",
        "source": "BMKG & Kementan",
        "content": (
            "Musim tanam 1 (Oktober-Maret): curah hujan tinggi, cocok selada, sawi, kangkung. "
            "Musim tanam 2 (April-September): kering, cocok tomat, cabai, melon. "
            "Dataran rendah (<200m): tomat cherry, kangkung, bayam, terong. "
            "Dataran menengah (200-700m): tomat, cabai, timun, buncis. "
            "Dataran tinggi (>700m): selada, brokoli, wortel, kentang, strawberry. "
            "Greenhouse mengatasi batasan musim — bisa tanam sepanjang tahun. "
            "Rotasi tanaman: minimal 2 famili berbeda berturut-turut."
        ),
    },
    {
        "title": "Analisis Ekonomi Greenhouse Indonesia",
        "source": "Kementan RI",
        "content": (
            "Investasi greenhouse 500 m2: Rp 150-300 juta (struktur + sistem). "
            "Biaya operasional: Rp 3-5 juta/bulan (listrik, pupuk, tenaga kerja). "
            "Revenue tomat: 60 ton/ha/thn x Rp 12.000/kg = Rp 72 juta/1000m2. "
            "Revenue cabai: 20 ton/ha/thn x Rp 45.000/kg = Rp 90 juta/1000m2. "
            "Revenue selada hidroponik: 15 panen/thn x 3000 kepala x Rp 5.000 = Rp 225 juta/1000m2. "
            "Payback period: 2-4 tahun untuk greenhouse standar. "
            "ROI: 25-60% per tahun tergantung komoditas dan manajemen. "
            "Carbon credit: Rp 3.000/kg CO2 tersequestrasi."
        ),
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# VECTOR EMBEDDINGS — Gemini text-embedding-004 (768 dimensi)
# ══════════════════════════════════════════════════════════════════════════════

# In-memory cache: list of (embedding_vector, text)
_DOC_EMBEDDINGS: List[Tuple[List[float], str]] = []
_EMBEDDINGS_READY = False


def _get_embedding(text: str, task_type: str = "retrieval_document") -> Optional[List[float]]:
    """Generate embedding via Gemini text-embedding-004.

    Returns None if GEMINI_API_KEY not set or API call fails.
    task_type: 'retrieval_document' untuk indexing, 'retrieval_query' untuk query.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type=task_type,
        )
        return result["embedding"]
    except Exception:
        return None


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity antara dua embedding vector."""
    dot   = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _ensure_doc_embeddings() -> bool:
    """Lazy-init: embed semua SEED_DOCUMENTS saat pertama kali retrieve() dipanggil.

    Returns True jika semua embedding berhasil di-cache.
    """
    global _DOC_EMBEDDINGS, _EMBEDDINGS_READY
    if _EMBEDDINGS_READY:
        return True

    embeddings: List[Tuple[List[float], str]] = []
    for doc in SEED_DOCUMENTS:
        text = f"[{doc['title']}] {doc['content']}"
        emb  = _get_embedding(text, task_type="retrieval_document")
        if emb is None:
            # Gagal (no API key atau error) — abort, pakai keyword fallback
            return False
        embeddings.append((emb, text))

    _DOC_EMBEDDINGS  = embeddings
    _EMBEDDINGS_READY = True
    return True


def _try_save_embedding_to_db(doc_id: int, chunk_idx: int,
                               content: str, embedding: List[float]) -> bool:
    """Simpan embedding ke Supabase knowledge_chunks (butuh pgvector aktif).

    Best-effort — gagal diam-diam jika pgvector belum diaktifkan.
    """
    try:
        from db.supabase_client import client
        c = client()
        if not c:
            return False
        c.table("knowledge_chunks").insert({
            "document_id": doc_id,
            "chunk_index": chunk_idx,
            "content":     content,
            "embedding":   embedding,
        }).execute()
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# SEED & RETRIEVAL
# ══════════════════════════════════════════════════════════════════════════════

def seed_knowledge() -> int:
    """Seed knowledge documents + embeddings ke Supabase.

    Urutan:
      1. Insert teks ke knowledge_documents
      2. Generate embedding tiap dokumen (jika GEMINI_API_KEY ada)
      3. Simpan ke knowledge_chunks.embedding (jika pgvector aktif)

    Returns jumlah dokumen yang berhasil di-seed.
    """
    count = 0
    for idx, doc in enumerate(SEED_DOCUMENTS):
        try:
            from db.supabase_client import client
            c = client()
            if not c:
                break

            # Insert/upsert ke knowledge_documents
            result = c.table("knowledge_documents").insert({
                "title":    doc["title"],
                "source":   doc["source"],
                "content":  doc["content"],
                "language": "id",
            }).execute()

            doc_id = result.data[0]["id"] if result.data else None
            count += 1

            # Generate & simpan embedding jika ada
            if doc_id:
                text = f"[{doc['title']}] {doc['content']}"
                emb  = _get_embedding(text, task_type="retrieval_document")
                if emb:
                    _try_save_embedding_to_db(doc_id, 0, text, emb)

        except Exception:
            break

    return count


def retrieve(query: str, top_k: int = 3) -> List[str]:
    """Retrieve top-K potongan dokumen paling relevan untuk query.

    Priority:
      1. Semantic vector search (Gemini embedding + cosine similarity) — jika GEMINI_API_KEY set
      2. Keyword matching fallback — selalu tersedia

    Returns list of text strings (format: "[Title] content...").
    """
    # ── 1. Vector search ──────────────────────────────────────────────────────
    if _ensure_doc_embeddings():
        query_emb = _get_embedding(query, task_type="retrieval_query")
        if query_emb and _DOC_EMBEDDINGS:
            scored = [
                (_cosine_similarity(query_emb, doc_emb), text)
                for doc_emb, text in _DOC_EMBEDDINGS
            ]
            scored.sort(key=lambda x: -x[0])
            results = [text for sim, text in scored[:top_k] if sim > 0.0]
            if results:
                return results

    # ── 2. Keyword fallback ──────────────────────────────────────────────────
    query_lower = query.lower()
    scored_kw: List[Tuple[int, str]] = []

    for doc in SEED_DOCUMENTS:
        text_lower = (doc["title"] + " " + doc["content"]).lower()
        words      = set(query_lower.split())
        score      = sum(1 for w in words if w in text_lower)
        score     += sum(2 for w in words if w in doc["title"].lower())
        if score > 0:
            scored_kw.append((score, f"[{doc['title']}] {doc['content']}"))

    scored_kw.sort(key=lambda x: -x[0])
    return [text for _, text in scored_kw[:top_k]]


def build_rag_prompt(user_query: str, top_k: int = 3) -> str:
    """Build system prompt dengan RAG context injection."""
    chunks = retrieve(user_query, top_k=top_k)

    if not chunks:
        return user_query

    context = "\n\n".join(f"📚 {c}" for c in chunks)
    return (
        "Kamu adalah AI agronomist Indonesia. Gunakan KONTEKS berikut untuk "
        "menjawab pertanyaan petani. Jawab dalam bahasa Indonesia yang jelas "
        "dan praktis. Berikan angka spesifik (suhu, dosis, waktu).\n\n"
        f"=== KONTEKS AGRONOMI ===\n{context}\n\n"
        f"=== PERTANYAAN ===\n{user_query}"
    )
