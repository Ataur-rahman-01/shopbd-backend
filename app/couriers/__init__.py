"""Courier integrations. Each client exposes:
- create_consignment(order) -> {"consignment_id": ..., "tracking_code": ..., "raw": ...}
- track(identifier) -> delivery_status string
Raises CourierError on any API/network failure (callers map it to HTTP 502).
"""

from .base import CourierError


def get_courier(provider: str, api_key: str, secret_key: str):
    provider = (provider or "").strip().lower()
    if provider == "steadfast":
        from .steadfast import SteadfastClient

        return SteadfastClient(api_key, secret_key)
    if provider == "pathao":
        from .pathao import PathaoClient

        return PathaoClient(api_key, secret_key)
    raise CourierError(f"Unknown courier provider: {provider!r}")


__all__ = ["get_courier", "CourierError"]
