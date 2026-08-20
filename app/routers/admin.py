from datetime import datetime, timezone, timedelta
from typing import Optional
import csv
import io
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_admin
from ..couriers import CourierError, get_courier
from ..database import get_db
from ..sms import send_order_confirmation_sms, SmsError

router = APIRouter(prefix="/api/admin", tags=["admin"])

STATUSES = {"pending", "confirmed", "shipped", "delivered", "cancelled"}


# ---------- Orders ----------
@router.get("/orders", response_model=list[schemas.OrderOut])
def list_orders(
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    q = db.query(models.Order)
    if status:
        q = q.filter(models.Order.status == status)
    if search:
        q = q.filter(
            (models.Order.name.ilike(f"%{search}%"))
            | (models.Order.phone.ilike(f"%{search}%"))
            | (models.Order.address.ilike(f"%{search}%"))
        )
    return q.order_by(models.Order.created_at.desc()).limit(200).all()


@router.get("/orders/{order_id}", response_model=schemas.OrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@router.patch("/orders/{order_id}", response_model=schemas.OrderOut)
def update_order(
    order_id: int,
    data: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    if data.status not in STATUSES:
        raise HTTPException(400, f"Status must be one of: {sorted(STATUSES)}")
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    order.status = data.status
    if data.courier_tracking is not None:
        order.courier_tracking = data.courier_tracking
    # Admin correction of recipient / shipping location
    if data.name is not None:
        order.name = data.name
    if data.phone is not None:
        order.phone = data.phone
    if data.address is not None:
        order.address = data.address
    if data.district is not None:
        order.district = data.district
    db.commit()
    db.refresh(order)

    # Send SMS when order is confirmed (skip if SMS not configured)
    if data.status == "confirmed":
        try:
            s = db.get(models.Settings, 1)
            send_order_confirmation_sms(s, order)
        except SmsError:
            pass  # SMS failure shouldn't block the order update

    return order


# ---------- Courier integration ----------
def courier_config(db: Session) -> dict:
    """Which provider is active + whether its credentials are complete."""
    s = db.get(models.Settings, 1)
    provider = (s.courier_provider or "").strip().lower()
    has_keys = bool(s.courier_api_key and s.courier_api_key.strip())
    if provider in ("steadfast", "pathao"):
        has_keys = has_keys and bool(s.courier_secret_key and s.courier_secret_key.strip())
    return {
        "provider": provider or None,
        "configured": bool(provider) and has_keys,
        "implemented": provider in ("steadfast", "pathao"),
    }


@router.get("/courier-config")
def get_courier_config(
    db: Session = Depends(get_db), _admin: models.AdminUser = Depends(get_current_admin)
):
    """Tells the admin UI whether the 'কুরিয়ারে পাঠান' button should render."""
    return courier_config(db)


@router.post("/orders/{order_id}/courier", response_model=schemas.OrderOut)
def send_to_courier(
    order_id: int,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    """Create a courier consignment for a confirmed/shipped order.

    Saves courier_id + courier_tracking on the order and moves it to shipped.
    """
    cfg = courier_config(db)
    if not cfg["configured"]:
        raise HTTPException(400, "কুরিয়ার API কনফিগার করা নেই — সেটিংসে কুরিয়ার প্রোভাইডার ও API Key দিন")
    if not cfg["implemented"]:
        raise HTTPException(400, f"'{cfg['provider']}' কুরিয়ারের API এখনো যোগ করা হয়নি — ম্যানুয়াল ফ্লো ব্যবহার করুন")

    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status not in ("confirmed", "shipped"):
        raise HTTPException(400, "শুধু কনফার্মড/শিপড অর্ডার কুরিয়ারে পাঠানো যায়")
    if order.courier_id:
        raise HTTPException(400, f"এই অর্ডার আগেই কুরিয়ারে পাঠানো হয়েছে (consignment {order.courier_id})")

    client = get_courier(cfg["provider"], db.get(models.Settings, 1).courier_api_key, db.get(models.Settings, 1).courier_secret_key)
    try:
        result = client.create_consignment(order)
    except CourierError as exc:
        raise HTTPException(502, f"কুরিয়ার API সমস্যা: {exc}")

    order.courier_id = str(result["consignment_id"])
    order.courier_tracking = str(result["tracking_code"])
    if order.status == "confirmed":
        order.status = "shipped"
    db.commit()
    db.refresh(order)
    return order


@router.get("/orders/{order_id}/courier-status", response_model=schemas.CourierStatusOut)
def admin_courier_status(
    order_id: int,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    """Live courier status for an order (admin — phone not required).

    Shows whether the order succeeded on the courier provider (delivered =
    success). Degrades gracefully if no courier / unconfigured / API error.
    """
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if not order.courier_id and not order.courier_tracking:
        return schemas.CourierStatusOut(
            detail="এই অর্ডার কুরিয়ারে পাঠানো হয়নি (courier_id নেই)"
        )
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
    return schemas.CourierStatusOut(**payload)


# ---------- Products ----------
@router.get("/products", response_model=list[schemas.ProductOut])
def admin_products(
    db: Session = Depends(get_db), _admin: models.AdminUser = Depends(get_current_admin)
):
    return db.query(models.Product).order_by(models.Product.created_at.desc()).all()


@router.post("/products", response_model=schemas.ProductOut)
def create_product(
    data: schemas.ProductIn,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    product = models.Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/products/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    data: schemas.ProductIn,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    for field, value in data.model_dump().items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    # Products that appear in past orders can't be hard-deleted (order_items
    # FK, and it would rewrite invoice/report history). Deactivate instead.
    has_orders = (
        db.query(models.OrderItem.id)
        .filter(models.OrderItem.product_id == product_id)
        .first()
        is not None
    )
    if has_orders:
        product.active = False
        db.commit()
        return {"deactivated": product_id}
    db.delete(product)
    db.commit()
    return {"deleted": product_id}


# ---------- Reviews ----------
@router.get("/reviews", response_model=list[schemas.AdminReviewOut])
def list_reviews(
    db: Session = Depends(get_db), _admin: models.AdminUser = Depends(get_current_admin)
):
    """All reviews (pending + approved) for the admin panel, newest first."""
    reviews = db.query(models.Review).order_by(models.Review.created_at.desc()).limit(500).all()
    names = dict(db.query(models.Product.id, models.Product.name).all())
    out = []
    for r in reviews:
        item = schemas.AdminReviewOut.model_validate(r)
        item.product_name = names.get(r.product_id, "")
        out.append(item)
    return out


@router.patch("/reviews/{review_id}/approve", response_model=schemas.ReviewOut)
def approve_review(
    review_id: int,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    review = db.get(models.Review, review_id)
    if not review:
        raise HTTPException(404, "Review not found")
    review.approved = True
    db.commit()
    db.refresh(review)
    return review


@router.delete("/reviews/{review_id}")
def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    review = db.get(models.Review, review_id)
    if not review:
        raise HTTPException(404, "Review not found")
    db.delete(review)
    db.commit()
    return {"deleted": review_id}


# ---------- Coupons ----------
@router.get("/coupons", response_model=list[schemas.CouponOut])
def list_coupons(
    db: Session = Depends(get_db), _admin: models.AdminUser = Depends(get_current_admin)
):
    return db.query(models.Coupon).order_by(models.Coupon.created_at.desc()).all()


@router.post("/coupons", response_model=schemas.CouponOut)
def create_coupon(
    data: schemas.CouponIn,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    if data.type not in ("percent", "fixed"):
        raise HTTPException(400, "type must be 'percent' or 'fixed'")
    code = data.code.strip().upper()
    if not code:
        raise HTTPException(400, "Coupon code required")
    exists = db.query(models.Coupon).filter(models.Coupon.code == code).first()
    if exists:
        raise HTTPException(400, f"কুপন '{code}' আগে থেকেই আছে (Code already exists)")
    coupon = models.Coupon(**{**data.model_dump(), "code": code})
    db.add(coupon)
    db.commit()
    db.refresh(coupon)
    return coupon


@router.put("/coupons/{coupon_id}", response_model=schemas.CouponOut)
def update_coupon(
    coupon_id: int,
    data: schemas.CouponIn,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    coupon = db.get(models.Coupon, coupon_id)
    if not coupon:
        raise HTTPException(404, "Coupon not found")
    if data.type not in ("percent", "fixed"):
        raise HTTPException(400, "type must be 'percent' or 'fixed'")
    new_code = data.code.strip().upper()
    clash = (
        db.query(models.Coupon)
        .filter(models.Coupon.code == new_code, models.Coupon.id != coupon_id)
        .first()
    )
    if clash:
        raise HTTPException(400, f"কুপন '{new_code}' আগে থেকেই আছে (Code already exists)")
    fields = data.model_dump()
    fields["code"] = new_code
    for field, value in fields.items():
        setattr(coupon, field, value)
    db.commit()
    db.refresh(coupon)
    return coupon


@router.delete("/coupons/{coupon_id}")
def delete_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    coupon = db.get(models.Coupon, coupon_id)
    if not coupon:
        raise HTTPException(404, "Coupon not found")
    db.delete(coupon)
    db.commit()
    return {"deleted": coupon_id}


# ---------- Dashboard ----------
@router.get("/dashboard", response_model=schemas.DashboardOut)
def dashboard(
    db: Session = Depends(get_db), _admin: models.AdminUser = Depends(get_current_admin)
):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    orders_today = (
        db.query(func.count(models.Order.id))
        .filter(models.Order.created_at >= today_start)
        .scalar()
        or 0
    )
    revenue_today = (
        db.query(func.coalesce(func.sum(models.Order.total), 0))
        .filter(models.Order.created_at >= today_start, models.Order.status != "cancelled")
        .scalar()
        or 0.0
    )
    pending_orders = (
        db.query(func.count(models.Order.id)).filter(models.Order.status == "pending").scalar()
        or 0
    )
    total_products = db.query(func.count(models.Product.id)).scalar() or 0
    low_stock_products = (
        db.query(func.count(models.Product.id))
        .filter(models.Product.stock <= 5, models.Product.active == True)  # noqa: E712
        .scalar()
        or 0
    )
    return schemas.DashboardOut(
        orders_today=orders_today,
        revenue_today=revenue_today,
        pending_orders=pending_orders,
        total_products=total_products,
        low_stock_products=low_stock_products,
    )


# ---------- Sales Reports ----------
@router.get("/reports", response_model=schemas.ReportOut)
def sales_report(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    """Sales report for a date range. Defaults to last 30 days."""
    now = datetime.now(timezone.utc)
    try:
        if to_date:
            end = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        else:
            end = now
        if from_date:
            start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            start = end - timedelta(days=29)
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        raise HTTPException(400, "Invalid date format — use YYYY-MM-DD")

    orders_q = db.query(models.Order).filter(
        models.Order.created_at >= start, models.Order.created_at <= end
    )

    total_orders = orders_q.count()
    cancelled_orders = orders_q.filter(models.Order.status == "cancelled").count()

    # Revenue excludes cancelled
    active_q = orders_q.filter(models.Order.status != "cancelled")
    total_revenue = db.query(func.coalesce(func.sum(active_q.subquery().c.total), 0)).scalar() or 0.0
    total_delivery = db.query(func.coalesce(func.sum(active_q.subquery().c.delivery_charge), 0)).scalar() or 0.0
    total_discount = db.query(func.coalesce(func.sum(active_q.subquery().c.discount), 0)).scalar() or 0.0

    # Daily sales (orders per day + revenue per day)
    daily_rows = (
        db.query(
            func.date(models.Order.created_at).label("d"),
            func.count(models.Order.id).label("cnt"),
            func.sum(models.Order.total).label("rev"),
        )
        .filter(
            models.Order.created_at >= start,
            models.Order.created_at <= end,
            models.Order.status != "cancelled",
        )
        .group_by(func.date(models.Order.created_at))
        .order_by(func.date(models.Order.created_at))
        .all()
    )
    daily_sales = [schemas.DailySales(date=str(r.d), orders=r.cnt, revenue=float(r.rev or 0)) for r in daily_rows]

    # Top 5 products by qty
    top_rows = (
        db.query(
            models.OrderItem.product_id,
            models.OrderItem.product_name,
            func.sum(models.OrderItem.qty).label("qty"),
            func.sum(models.OrderItem.price * models.OrderItem.qty).label("rev"),
        )
        .join(models.Order, models.OrderItem.order_id == models.Order.id)
        .filter(
            models.Order.created_at >= start,
            models.Order.created_at <= end,
            models.Order.status != "cancelled",
        )
        .group_by(models.OrderItem.product_id, models.OrderItem.product_name)
        .order_by(func.sum(models.OrderItem.qty).desc())
        .limit(5)
        .all()
    )
    top_products = [
        schemas.TopProduct(product_id=r.product_id, product_name=r.product_name, qty_sold=int(r.qty), revenue=float(r.rev or 0))
        for r in top_rows
    ]

    return schemas.ReportOut(
        total_orders=total_orders,
        total_revenue=float(total_revenue),
        total_delivery_charge=float(total_delivery),
        total_discount=float(total_discount),
        cancelled_orders=cancelled_orders,
        daily_sales=daily_sales,
        top_products=top_products,
    )


@router.get("/reports/export")
def export_report_csv(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    """Export order list with items as CSV for the date range."""
    now = datetime.now(timezone.utc)
    try:
        if to_date:
            end = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        else:
            end = now
        if from_date:
            start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            start = end - timedelta(days=29)
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        raise HTTPException(400, "Invalid date format — use YYYY-MM-DD")

    orders = (
        db.query(models.Order)
        .filter(models.Order.created_at >= start, models.Order.created_at <= end)
        .order_by(models.Order.created_at.desc())
        .all()
    )

    output = io.StringIO()
    # UTF-8 BOM so Excel opens Bangla text correctly (no mojibake)
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "Order ID", "Date", "Customer", "Phone", "District", "Address",
        "Items", "Subtotal", "Delivery Charge", "Discount", "Total", "Status"
    ])
    for o in orders:
        items_str = "; ".join(f"{i.product_name} x{i.qty}" for i in o.items)
        created = o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else ""
        writer.writerow([
            o.id, created, o.name, o.phone, o.district or "", o.address,
            items_str, o.subtotal, o.delivery_charge, o.discount, o.total, o.status
        ])

    output.seek(0)
    fname = f"shopbd_report_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ---------- Image uploads ----------
# Allowed image extensions + the on-disk upload dir (shared under /media).
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")


def _image_ext(filename: str) -> str:
    ext = (os.path.splitext(filename or "")[1] or "").lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(400, "শুধু ছবি আপলোড করুন (PNG, JPG, GIF, WEBP, SVG)")
    return ext


@router.post("/upload")
def upload_image(
    file: UploadFile = File(...),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    """Upload an image (logo / product photo). Returns the public /media URL."""
    ext = _image_ext(file.filename or "")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(UPLOAD_DIR, fname)
    with open(dest, "wb") as out:
        # Stream in chunks so large photos don't bloat memory.
        for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
            out.write(chunk)
    return {"url": f"/media/{fname}"}
