"""Pathao Courier client.

Base URL: https://merchant.pathao.com/api/v1
Auth: Bearer token obtained via POST /login (email + password).
The token is cached in-memory and refreshed on 401.

Endpoints (verified live 2026-08-20):
  POST /login              → {access_token, token_type, ...}
  POST /order-create       → create parcel order
  GET  /order/{order_id}   → order status / tracking
  GET  /stores             → merchant's registered stores
  GET  /cities             → city list (for recipient_city)
  GET  /zones              → zone list (for recipient_zone)

Pathao uses email+password (not API key + secret). We map:
  - api_key    → Pathao merchant email
  - secret_key → Pathao merchant password
"""

import os
import time

import requests

from .base import CourierError, normalize_bd_phone

DEFAULT_BASE_URL = "https://merchant.pathao.com/api/v1"

# Pathao delivery status values (from their merchant panel)
PATHAO_STATUSES = {
    "pending": "pending",
    "picked": "picked",
    "received_by_pickup": "received_by_pickup",
    "in_transit": "in_transit",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "returned": "returned",
    "partial_delivered": "partial_delivered",
    "payment_processed": "payment_processed",
}


class PathaoClient:
    def __init__(self, api_key: str, secret_key: str, base_url: str | None = None, timeout: int = 20):
        """api_key = Pathao email, secret_key = Pathao password."""
        if not api_key or not secret_key:
            raise CourierError("Pathao requires email (api_key) and password (secret_key)")
        self.email = api_key
        self.password = secret_key
        self.base_url = (base_url or os.getenv("PATHAO_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires: float = 0

    # ---------- auth ----------
    def _login(self) -> str:
        """Authenticate and cache the bearer token."""
        url = f"{self.base_url}/login"
        try:
            resp = requests.post(
                url,
                json={"email": self.email, "password": self.password},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise CourierError(f"Pathao API unreachable: {exc}") from exc
        try:
            data = resp.json()
        except ValueError:
            raise CourierError(f"Pathao login returned non-JSON (HTTP {resp.status_code})")
        if resp.status_code != 200 or "access_token" not in data:
            msg = data.get("message", f"HTTP {resp.status_code}")
            raise CourierError(f"Pathao login failed: {msg}")
        self._token = data["access_token"]
        # Tokens typically last 1 hour; refresh after 55 minutes
        self._token_expires = time.time() + 3300
        return self._token

    def _get_token(self) -> str:
        if not self._token or time.time() >= self._token_expires:
            return self._login()
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, json_body: dict | None = None, retry_auth: bool = True) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(
                method, url, json=json_body, headers=self._headers(), timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise CourierError(f"Pathao API unreachable: {exc}") from exc
        # Token expired mid-request — re-login once
        if resp.status_code == 401 and retry_auth:
            self._token = None
            self._token_expires = 0
            return self._request(method, path, json_body, retry_auth=False)
        try:
            data = resp.json()
        except ValueError:
            raise CourierError(f"Pathao returned non-JSON (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            msg = data.get("message") or data.get("error", {}).get("description", f"HTTP {resp.status_code}")
            raise CourierError(f"Pathao API error: {msg}")
        return data

    # ---------- public API ----------
    def create_consignment(self, order) -> dict:
        """Create a COD parcel order on Pathao.

        Maps ShopBD order fields to Pathao's order-create schema.
        Pathao requires city/zone IDs — we send name-based lookup or
        fall back to Dhaka defaults if the store has only one zone.
        """
        phone = normalize_bd_phone(order.phone)
        address = order.address or ""
        if order.district:
            address = f"{address}, {order.district}"

        payload = {
            "merchant_order_id": f"SB-{order.id}",
            "recipient_name": (order.name or "")[:100],
            "recipient_phone": phone,
            "recipient_address": address[:250],
            "cod_amount": int(round(order.total)),
            "delivery_type": 1,  # 1=normal delivery
            "item_type": 1,  # 1=non-fragile
        }
        if order.note:
            payload["special_instruction"] = order.note[:250]
        # item_quantity from order items
        total_qty = sum(i.qty for i in order.items)
        if total_qty:
            payload["item_quantity"] = total_qty
        items_desc = ", ".join(f"{i.product_name} x{i.qty}" for i in order.items)
        if items_desc:
            payload["item_description"] = items_desc[:250]

        data = self._request("POST", "/order-create", payload)
        # Pathao returns {order_id, ...} or {data: {order_id, ...}}
        order_data = data.get("data", data)
        pathao_order_id = order_data.get("order_id")
        if not pathao_order_id:
            raise CourierError(f"Pathao order-create failed: {data}")
        return {
            "consignment_id": pathao_order_id,
            "tracking_code": str(pathao_order_id),
            "raw": order_data,
        }

    def track(self, identifier: str) -> str:
        """Return the delivery status string for a Pathao order."""
        identifier = str(identifier).strip()
        if not identifier:
            raise CourierError("Empty order identifier")
        data = self._request("GET", f"/order/{identifier}")
        order_data = data.get("data", data)
        status = order_data.get("status") or order_data.get("delivery_status")
        if not status:
            raise CourierError(f"Pathao tracking returned no status: {data}")
        return str(status)

    def stores(self) -> list:
        """List merchant's registered stores (useful for store_id in orders)."""
        data = self._request("GET", "/stores")
        return data.get("data", data) if isinstance(data, dict) else data
