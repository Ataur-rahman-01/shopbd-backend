from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import decode_token
from ..couriers import CourierError, get_courier
from ..database import get_db
from .coupons import compute_discount, validate_coupon

router = APIRouter(prefix="/api/orders", tags=["orders"])

DHAKA_MARKERS = ("dhaka", "ঢাকা")


def _delivery_charge(subtotal: float, district: Optional[str], s: models.Settings) -> float:
    if s.free_delivery_threshold and subtotal >= s.free_delivery_threshold:
        return 0.0
    inside = False
    if district:
        inside = any(m in district.lower() for m in DHAKA_MARKERS)
    return s.delivery_inside if inside else s.delivery_outside


@router.post("", response_model=schemas.OrderOut)
def create_order(order: schemas.OrderIn, request: Request, db: Session = Depends(get_db)):
    """Guest or logged-in checkout: name, phone, address + COD."""
    if not order.items:
        raise HTTPException(400, "Cart is empty")

    settings = db.get(models.Settings, 1)
    if not settings.store_open:
        raise HTTPException(400, "দুঃখিত, দোকানটি এখন বন্ধ আছে (Shop is currently closed)")

    subtotal = 0.0
    items: list[models.OrderItem] = []
    for line in order.items:
        if line.qty < 1:
            raise HTTPException(400, "Invalid quantity")
        product = db.get(models.Product, line.product_id)
        if not product or not product.active:
            raise HTTPException(404, f"Product {line.product_id} not found")
        if product.stock < line.qty:
            raise HTTPException(400, f"Not enough stock for: {product.name}")
        product.stock -= line.qty
        subtotal += product.price * line.qty
        items.append(
            models.OrderItem(
                product_id=product.id,
                product_name=product.name,
                price=product.price,
                qty=line.qty,
            )
        )

    delivery = _delivery_charge(subtotal, order.district, settings)

    # Apply coupon (validated server-side; re-checked against real subtotal)
    discount = 0.0
    coupon_code: Optional[str] = None
    if order.coupon_code and order.coupon_code.strip():
        coupon = validate_coupon(db, order.coupon_code, subtotal)
        discount = compute_discount(coupon, subtotal)
        coupon_code = coupon.code
        coupon.used_count += 1

    # Attach logged-in customer if a valid token is present (optional)
    customer_id: Optional[int] = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        payload = decode_token(auth.split(" ", 1)[1])
        if payload and payload.get("role") == "customer":
            customer_id = int(payload["sub"])

    db_order = models.Order(
        customer_id=customer_id,
        name=order.name,
        phone=order.phone,
        address=order.address,
        district=order.district,
        note=order.note,
        subtotal=subtotal,
        delivery_charge=delivery,
        discount=discount,
        coupon_code=coupon_code,
        total=subtotal + delivery - discount,
        items=items,
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order


@router.get("/track", response_model=list[schemas.OrderTrackOut])
def track_orders(phone: str, db: Session = Depends(get_db)):
    """Public order tracking: customer enters their phone number."""
    return (
        db.query(models.Order)
        .filter(models.Order.phone == phone)
        .order_by(models.Order.created_at.desc())
        .all()
    )


# ---------- Live courier tracking ----------
_courier_cache: dict[int, tuple[float, dict]] = {}  # order_id -> (ts, payload)
_CACHE_TTL = 60.0  # seconds; courier status updates every ~5 min anyway


@router.get("/courier-track/{order_id}", response_model=schemas.CourierStatusOut)
def courier_track(order_id: int, phone: str, db: Session = Depends(get_db)):
    """Live status from the courier for one order.

    Phone must match the order (public endpoint). Degrades gracefully:
    no courier on the order / provider unconfigured -> delivery_status None.
    """
    from time import time

    order = db.get(models.Order, order_id)
    if not order or order.phone.strip() != phone.strip():
        raise HTTPException(404, "Order not found for this phone number")
    if not order.courier_id and not order.courier_tracking:
        return schemas.CourierStatusOut()

    cached = _courier_cache.get(order_id)
    if cached and time() - cached[0] < _CACHE_TTL:
        return schemas.CourierStatusOut(**cached[1])

    s = db.get(models.Settings, 1)
    provider = (s.courier_provider or "").strip().lower()
    payload: dict = {
        "provider": provider,
        "courier_id": order.courier_id,
        "courier_tracking": order.courier_tracking,
        "delivery_status": None,
        "detail": None,
    }
    if provider and s.courier_api_key:
        try:
            client = get_courier(provider, s.courier_api_key, s.courier_secret_key)
            identifier = order.courier_id or order.courier_tracking
            payload["delivery_status"] = client.track(identifier)
        except CourierError as exc:
            payload["detail"] = str(exc)
    else:
        payload["detail"] = "কুরিয়ার API কনফিগার করা নেই"

    _courier_cache[order_id] = (time(), payload)
    return schemas.CourierStatusOut(**payload)
