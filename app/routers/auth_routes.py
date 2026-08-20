from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import create_token, get_current_customer, hash_password, verify_password
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenOut)
def register(data: schemas.CustomerRegister, db: Session = Depends(get_db)):
    """Customer account: phone + password. No OTP."""
    exists = db.query(models.Customer).filter(models.Customer.phone == data.phone).first()
    if exists:
        raise HTTPException(400, "এই নম্বরে আগেই একাউন্ট আছে (Phone already registered)")
    customer = models.Customer(
        phone=data.phone,
        name=data.name,
        password_hash=hash_password(data.password),
        address=data.address,
        district=data.district,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return {"access_token": create_token(str(customer.id), "customer")}


@router.post("/login", response_model=schemas.TokenOut)
def login(data: schemas.CustomerLogin, db: Session = Depends(get_db)):
    customer = db.query(models.Customer).filter(models.Customer.phone == data.phone).first()
    if not customer or not verify_password(data.password, customer.password_hash):
        raise HTTPException(401, "ভুল নম্বর বা পাসওয়ার্ড (Wrong phone or password)")
    return {"access_token": create_token(str(customer.id), "customer")}


@router.post("/admin/login", response_model=schemas.TokenOut)
def admin_login(data: schemas.AdminLogin, db: Session = Depends(get_db)):
    user = db.query(models.AdminUser).filter(models.AdminUser.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Wrong username or password")
    return {"access_token": create_token(str(user.id), user.role)}


@router.get("/me", response_model=schemas.CustomerOut)
def me(customer: models.Customer = Depends(get_current_customer)):
    return customer


@router.put("/profile", response_model=schemas.CustomerOut)
def update_profile(
    data: schemas.CustomerProfileUpdate,
    customer: models.Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """Customer updates their own profile (name, address, district)."""
    if data.name is not None:
        customer.name = data.name
    if data.address is not None:
        customer.address = data.address
    if data.district is not None:
        customer.district = data.district
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/orders", response_model=list[schemas.OrderOut])
def customer_orders(
    customer: models.Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """Logged-in customer's own orders."""
    return (
        db.query(models.Order)
        .filter(models.Order.customer_id == customer.id)
        .order_by(models.Order.created_at.desc())
        .all()
    )
