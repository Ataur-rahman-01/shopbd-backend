from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_admin
from ..database import get_db

router = APIRouter(prefix="/api/admin/faqs", tags=["faq"])


@router.get("", response_model=list[schemas.FaqOut])
def list_faqs(
    db: Session = Depends(get_db), _admin: models.AdminUser = Depends(get_current_admin)
):
    """All FAQs (incl. inactive) for the editor."""
    return db.query(models.Faq).order_by(models.Faq.sort_order, models.Faq.id).all()


@router.post("", response_model=schemas.FaqOut)
def create_faq(
    data: schemas.FaqIn,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    faq = models.Faq(**data.model_dump())
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


@router.put("/{faq_id}", response_model=schemas.FaqOut)
def update_faq(
    faq_id: int,
    data: schemas.FaqIn,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    faq = db.get(models.Faq, faq_id)
    if not faq:
        raise HTTPException(404, "FAQ not found")
    for field, value in data.model_dump().items():
        setattr(faq, field, value)
    db.commit()
    db.refresh(faq)
    return faq


@router.delete("/{faq_id}")
def delete_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    faq = db.get(models.Faq, faq_id)
    if not faq:
        raise HTTPException(404, "FAQ not found")
    db.delete(faq)
    db.commit()
    return {"deleted": faq_id}


@router.post("/reorder")
def reorder_faqs(
    ids: list[int],
    db: Session = Depends(get_db),
    _admin: models.AdminUser = Depends(get_current_admin),
):
    """Body = FAQ ids in desired display order."""
    for order, faq_id in enumerate(ids, start=1):
        faq = db.get(models.Faq, faq_id)
        if faq:
            faq.sort_order = order
    db.commit()
    return {"ok": True}
