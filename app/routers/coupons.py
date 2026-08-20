from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/coupons", tags=["coupons"])


def _is_expired(coupon: models.Coupon) -> bool:
    if not coupon.expires_at:
        return False
    exp = coupon.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp <= models.utcnow()


def _coupon_problem(coupon: models.Coupon | None, subtotal: float) -> str | None:
    """Return a Bangla error message if the coupon can't be used, else None."""
    if not coupon or not coupon.active:
        return "কুপন কোডটি সঠিক নয়।"
    if _is_expired(coupon):
        return "দুঃখিত, এই কুপনের মেয়াদ শেষ হয়ে গেছে।"
    if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
        return "দুঃখিত, এই কুপনের ব্যবহার শেষ হয়ে গেছে।"
    if subtotal < coupon.min_order:
        return f"এই কুপন ব্যবহার করতে কমপক্ষে ৳{coupon.min_order:g} এর অর্ডার করতে হবে।"
    return None


def compute_discount(coupon: models.Coupon, subtotal: float) -> float:
    if coupon.type == "percent":
        discount = subtotal * coupon.value / 100
    else:  # fixed
        discount = coupon.value
    return round(min(discount, subtotal), 2)


def validate_coupon(db: Session, code: str, subtotal: float) -> models.Coupon:
    """Shared by POST /api/coupons/validate and order creation. Raises 400 with a
    Bangla message when the coupon is invalid; returns the coupon row otherwise."""
    coupon = (
        db.query(models.Coupon)
        .filter(models.Coupon.code == code.strip().upper())
        .first()
    )
    problem = _coupon_problem(coupon, subtotal)
    if problem:
        raise HTTPException(400, problem)
    return coupon


@router.post("/validate", response_model=schemas.CouponValidateOut)
def validate(data: schemas.CouponValidateIn, db: Session = Depends(get_db)):
    """Check a coupon before order placement; returns the discount amount."""
    coupon = validate_coupon(db, data.code, data.subtotal)
    discount = compute_discount(coupon, data.subtotal)
    return schemas.CouponValidateOut(
        code=coupon.code,
        discount=discount,
        message=f"কুপন প্রয়োগ হয়েছে! আপনি ৳{discount:g} ছাড় পাচ্ছেন।",
    )
