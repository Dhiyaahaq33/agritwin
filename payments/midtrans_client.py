"""
payments/midtrans_client.py — Midtrans Snap API client for AgriTwin
====================================================================
Foundation-level integration: create Snap transaction token + redirect URL.

Setup (gratis sandbox, no CC):
  1. Daftar di https://dashboard.midtrans.com/register
  2. Pilih mode Sandbox untuk testing
  3. Settings → Access Keys → copy Server Key & Client Key
  4. Isi di .env: MIDTRANS_SERVER_KEY, MIDTRANS_CLIENT_KEY

Referensi: https://docs.midtrans.com/reference/snap-api
"""
import base64
import os
from typing import Dict, Optional

import requests as _requests

# ── Config ────────────────────────────────────────────────────────────────────

def _snap_base_url() -> str:
    prod = os.environ.get("MIDTRANS_PRODUCTION", "false").lower() == "true"
    return (
        "https://app.midtrans.com/snap/v1"
        if prod
        else "https://app.sandbox.midtrans.com/snap/v1"
    )


def _auth_header() -> Optional[str]:
    key = os.environ.get("MIDTRANS_SERVER_KEY", "")
    if not key:
        return None
    encoded = base64.b64encode(f"{key}:".encode()).decode()
    return f"Basic {encoded}"


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def create_snap_transaction(
    order_id: str,
    amount: int,
    item_name: str,
    customer_name: str,
    customer_email: str,
    zone_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict:
    """Buat transaksi Midtrans Snap.

    Returns:
        {"token": str, "redirect_url": str, "order_id": str, "amount": int}
        atau {"error": str} jika gagal.

    Args:
        order_id:       ID unik transaksi (format: AGT-{timestamp}-{clerk_id})
        amount:         Jumlah pembayaran dalam IDR (integer, tanpa desimal)
        item_name:      Deskripsi item (misal: "AgriTwin Pro — 1 Bulan")
        customer_name:  Nama pelanggan
        customer_email: Email pelanggan (untuk struk)
        zone_id:        Opsional — zone terkait, disimpan di custom_field1
        user_id:        Opsional — Clerk user ID, disimpan di custom_field2 untuk webhook
    """
    auth = _auth_header()
    if not auth:
        return {"error": "MIDTRANS_SERVER_KEY tidak dikonfigurasi di .env"}

    payload = {
        "transaction_details": {
            "order_id":    order_id,
            "gross_amount": amount,
        },
        "item_details": [
            {
                "id":       "agritwin-subscription",
                "price":    amount,
                "quantity": 1,
                "name":     item_name[:50],  # Midtrans max 50 chars
            }
        ],
        "customer_details": {
            "first_name": customer_name,
            "email":      customer_email,
        },
        "callbacks": {
            "finish": os.environ.get("MIDTRANS_FINISH_URL", ""),
        },
        "custom_field1": zone_id or "",
        "custom_field2": user_id or "",
    }

    try:
        resp = _requests.post(
            f"{_snap_base_url()}/transactions",
            json=payload,
            headers={
                "Authorization": auth,
                "Content-Type":  "application/json",
            },
            timeout=15,
        )

        if not resp.ok:
            return {
                "error": f"Midtrans error {resp.status_code}: {resp.text[:200]}"
            }

        data = resp.json()
        return {
            "token":        data.get("token", ""),
            "redirect_url": data.get("redirect_url", ""),
            "order_id":     order_id,
            "amount":       amount,
        }

    except _requests.Timeout:
        return {"error": "Midtrans API timeout (>15s)"}
    except Exception as e:
        return {"error": f"Connection error: {str(e)[:100]}"}


def get_transaction_status(order_id: str) -> Dict:
    """Cek status transaksi Midtrans.

    Returns raw Midtrans status response atau {"error": str}.
    """
    auth = _auth_header()
    if not auth:
        return {"error": "MIDTRANS_SERVER_KEY tidak dikonfigurasi"}

    is_prod = os.environ.get("MIDTRANS_PRODUCTION", "false").lower() == "true"
    base = (
        "https://api.midtrans.com/v2"
        if is_prod
        else "https://api.sandbox.midtrans.com/v2"
    )

    try:
        resp = _requests.get(
            f"{base}/{order_id}/status",
            headers={"Authorization": auth},
            timeout=10,
        )
        return resp.json() if resp.ok else {"error": resp.text[:200]}
    except Exception as e:
        return {"error": str(e)[:100]}
