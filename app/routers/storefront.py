from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api", tags=["storefront"])


# ---------- Review rate limiting (1/hour per IP, in-memory) ----------
_REVIEW_WINDOW = timedelta(hours=1)
_review_hits: dict[str, datetime] = {}


def _check_review_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = datetime.utcnow()
    # Prune old entries occasionally
    if len(_review_hits) > 5000:
        stale = [k for k, v in _review_hits.items() if now - v > _REVIEW_WINDOW]
        for k in stale:
            _review_hits.pop(k, None)
    last = _review_hits.get(ip)
    if last and now - last < _REVIEW_WINDOW:
        remaining = int((_REVIEW_WINDOW - (now - last)).total_seconds() // 60) + 1
        raise HTTPException(429, f"১ ঘণ্টায় ১টি রিভিউ দেওয়া যায়। আবার চেষ্টা করুন ~{remaining} মিনিট পরে।")
    _review_hits[ip] = now


def _attach_ratings(products: list[schemas.ProductOut], db: Session) -> list[schemas.ProductOut]:
    """Fill avg_rating/review_count from approved reviews in one query."""
    if not products:
        return products
    ids = [p.id for p in products]
    rows = (
        db.query(
            models.Review.product_id,
            func.count(models.Review.id),
            func.avg(models.Review.rating),
        )
        .filter(models.Review.product_id.in_(ids), models.Review.approved == True)  # noqa: E712
        .group_by(models.Review.product_id)
        .all()
    )
    stats = {pid: (cnt, round(avg, 1)) for pid, cnt, avg in rows}
    for p in products:
        cnt, avg = stats.get(p.id, (0, None))
        p.review_count = cnt
        p.avg_rating = avg
    return products


@router.get("/settings/public", response_model=schemas.SettingsPublic)
def public_settings(db: Session = Depends(get_db)):
    """Branding + store config for the storefront (no secrets)."""
    return db.get(models.Settings, 1)


@router.get("/products", response_model=list[schemas.ProductOut])
def list_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Product).filter(models.Product.active == True)  # noqa: E712
    if category and category != "all":
        q = q.filter(models.Product.category == category)
    if search:
        q = q.filter(models.Product.name.ilike(f"%{search}%"))
    products = [schemas.ProductOut.model_validate(p) for p in q.order_by(models.Product.created_at.desc()).all()]
    return _attach_ratings(products, db)


@router.get("/products/{product_id}", response_model=schemas.ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Single product for the detail page."""
    product = db.get(models.Product, product_id)
    if not product or not product.active:
        raise HTTPException(404, "পণ্যটি পাওয়া যায়নি (Product not found)")
    return _attach_ratings([schemas.ProductOut.model_validate(product)], db)[0]


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    rows = (
        db.query(models.Product.category)
        .filter(models.Product.active == True)  # noqa: E712
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


@router.get("/pages/{slug}", response_model=schemas.PageOut)
def get_page(slug: str, db: Session = Depends(get_db)):
    """Public static page (About Us / Contact / FAQ)."""
    page = (
        db.query(models.Page)
        .filter(models.Page.slug == slug, models.Page.active == True)  # noqa: E712
        .first()
    )
    if not page:
        raise HTTPException(404, "পেজটি পাওয়া যায়নি (Page not found)")
    return page


@router.get("/faqs", response_model=list[schemas.FaqOut])
def list_faqs(db: Session = Depends(get_db)):
    """Public FAQ list for the /faq page, ordered by sort_order."""
    return (
        db.query(models.Faq)
        .filter(models.Faq.active == True)  # noqa: E712
        .order_by(models.Faq.sort_order, models.Faq.id)
        .all()
    )


# ---------- Reviews ----------
@router.get("/products/{product_id}/reviews", response_model=list[schemas.ReviewOut])
def list_reviews(product_id: int, db: Session = Depends(get_db)):
    """Approved reviews only, newest first."""
    return (
        db.query(models.Review)
        .filter(models.Review.product_id == product_id, models.Review.approved == True)  # noqa: E712
        .order_by(models.Review.created_at.desc())
        .all()
    )


@router.post("/products/{product_id}/reviews", response_model=schemas.ReviewOut, status_code=201)
def create_review(
    product_id: int,
    data: schemas.ReviewIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Public review submission. Pending until an admin approves it."""
    product = db.get(models.Product, product_id)
    if not product or not product.active:
        raise HTTPException(404, "পণ্যটি পাওয়া যায়নি (Product not found)")
    if not 1 <= data.rating <= 5:
        raise HTTPException(422, "রেটিং ১ থেকে ৫ এর মধ্যে হতে হবে")
    if not data.name.strip():
        raise HTTPException(422, "আপনার নাম লিখুন")
    _check_review_rate_limit(request)
    review = models.Review(
        product_id=product_id,
        name=data.name.strip()[:100],
        rating=data.rating,
        text=data.text.strip(),
        approved=False,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review
