"""Steadfast (Packzy portal) courier client.

Verified against the official Steadfast API docs (see docs/COURIER_API.md):
  Base URL: https://portal.packzy.com/api/v1   (old portal.steadfast.com.bd is dead)
  Auth:     Api-Key + Secret-Key headers on every request
  Create:   POST /create_order
  Status:   GET /status_by_cid/{id} | /status_by_invoice/{inv} | /status_by_trackingcode/{code}
"""

import os

import requests

from .base import CourierError, normalize_bd_phone

DEFAULT_BASE_URL = "https://portal.packzy.com/api/v1"


class SteadfastClient:
    def __init__(self, api_key: str, secret_key: str, base_url: str | None = None, timeout: int = 20):
        if not api_key or not secret_key:
            raise CourierError("Steadfast requires both Api-Key and Secret-Key")
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = (base_url or os.getenv("STEADFAST_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    # ---------- internals ----------
    def _headers(self) -> dict:
        return {
            "Api-Key": self.api_key,
            "Secret-Key": self.secret_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, json_body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(
                method, url, json=json_body, headers=self._headers(), timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise CourierError(f"Steadfast API unreachable: {exc}") from exc
        if resp.status_code in (401, 403):
            raise CourierError("Steadfast rejected the API credentials (check Api-Key/Secret-Key)")
        try:
            data = resp.json()
        except ValueError:
            raise CourierError(f"Steadfast returned non-JSON (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise CourierError(f"Steadfast HTTP {resp.status_code}: {data}")
        return data

    # ---------- public API ----------
    def create_consignment(self, order) -> dict:
        """Create a COD consignment for a shopbd Order row."""
        address = order.address or ""
        if order.district:
            address = f"{address}, {order.district}"
        payload = {
            "invoice": f"SB-{order.id}",
            "recipient_name": (order.name or "")[:100],
            "recipient_phone": normalize_bd_phone(order.phone),
            "recipient_address": address[:250],
            "cod_amount": int(round(order.total)),
            "delivery_type": 0,  # home delivery
        }
        if order.note:
            payload["note"] = order.note[:480]
        items_desc = ", ".join(f"{i.product_name} x{i.qty}" for i in order.items)
        if items_desc:
            payload["item_description"] = items_desc[:250]

        data = self._request("POST", "/create_order", payload)
        consignment = (data or {}).get("consignment")
        if not consignment or not consignment.get("consignment_id"):
            raise CourierError(f"Steadfast create_order failed: {data}")
        return {
            "consignment_id": consignment["consignment_id"],
            "tracking_code": consignment.get("tracking_code") or str(consignment["consignment_id"]),
            "raw": consignment,
        }

    def track(self, identifier: str) -> str:
        """Return the delivery_status string for a consignment id or tracking code.

        Numeric identifiers go to /status_by_cid, anything else to
        /status_by_trackingcode (matches how Steadfast issues ids vs codes).
        """
        identifier = str(identifier).strip()
        if not identifier:
            raise CourierError("Empty consignment identifier")
        path = f"/status_by_cid/{identifier}" if identifier.isdigit() else f"/status_by_trackingcode/{identifier}"
        data = self._request("GET", path)
        status = (data or {}).get("delivery_status")
        if not status:
            raise CourierError(f"Steadfast tracking returned no status: {data}")
        return status

    def balance(self) -> dict:
        return self._request("GET", "/get_balance")
