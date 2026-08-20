from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_superadmin, hash_password
from ..database import get_db

router = APIRouter(prefix="/api/admin", tags=["superadmin"])


@router.get("/settings", response_model=schemas.SettingsFull)
def get_settings(
    db: Session = Depends(get_db), _owner: models.AdminUser = Depends(get_superadmin)
):
    """Full settings incl. courier/SMS API keys — super admin only."""
    return db.get(models.Settings, 1)


@router.put("/settings", response_model=schemas.SettingsFull)
def update_settings(
    data: schemas.SettingsUpdate,
    db: Session = Depends(get_db),
    _owner: models.AdminUser = Depends(get_superadmin),
):
    """White-label rebrand + integrations. Storefront picks changes up live."""
    s = db.get(models.Settings, 1)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return s


# ---------- Static pages ----------
@router.get("/pages", response_model=list[schemas.PageOut])
def list_pages(
    db: Session = Depends(get_db), _owner: models.AdminUser = Depends(get_superadmin)
):
    return db.query(models.Page).order_by(models.Page.id).all()


@router.put("/pages/{slug}", response_model=schemas.PageOut)
def update_page(
    slug: str,
    data: schemas.PageUpdate,
    db: Session = Depends(get_db),
    _owner: models.AdminUser = Depends(get_superadmin),
):
    """Edit title/content/active of a static page. Storefront picks it up live."""
    page = db.query(models.Page).filter(models.Page.slug == slug).first()
    if not page:
        raise HTTPException(404, "Page not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(page, field, value)
    db.commit()
    db.refresh(page)
    return page


# ---------- Staff management ----------
@router.get("/users", response_model=list[schemas.AdminUserOut])
def list_users(
    db: Session = Depends(get_db), _owner: models.AdminUser = Depends(get_superadmin)
):
    """List all admin users (superadmin can manage staff)."""
    return db.query(models.AdminUser).order_by(models.AdminUser.created_at.desc()).all()


@router.post("/users", response_model=schemas.AdminUserOut)
def create_user(
    data: schemas.AdminUserCreate,
    db: Session = Depends(get_db),
    _owner: models.AdminUser = Depends(get_superadmin),
):
    """Create a new staff user (admin or superadmin)."""
    if data.role not in ("admin", "superadmin"):
        raise HTTPException(400, "Role must be 'admin' or 'superadmin'")
    exists = db.query(models.AdminUser).filter(models.AdminUser.username == data.username).first()
    if exists:
        raise HTTPException(400, "Username already exists")
    user = models.AdminUser(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    owner: models.AdminUser = Depends(get_superadmin),
):
    """Delete a staff user (cannot delete yourself)."""
    if user_id == owner.id:
        raise HTTPException(400, "Cannot delete your own account")
    user = db.get(models.AdminUser, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    db.delete(user)
    db.commit()
    return {"deleted": user_id}
