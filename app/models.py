from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdminUser(Base):
    """Shop staff. role: superadmin (owner) or admin (staff)."""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Customer(Base):
    """Optional customer account: phone + password (no OTP)."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    price: Mapped[float] = mapped_column(Float)
    original_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    image: Mapped[str] = mapped_column(String(500), default="")
    # Extra product photos (image URLs), 3-5 recommended. `image` stays the cover.
    gallery: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    category: Mapped[str] = mapped_column(String(60), default="general", index=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    badge: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20), index=True)
    address: Mapped[str] = mapped_column(Text)
    district: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subtotal: Mapped[float] = mapped_column(Float)
    delivery_charge: Mapped[float] = mapped_column(Float, default=0)
    discount: Mapped[float] = mapped_column(Float, default=0)
    coupon_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    total: Mapped[float] = mapped_column(Float)
    # pending -> confirmed -> shipped -> delivered (or cancelled)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    payment: Mapped[str] = mapped_column(String(20), default="cod")
    courier_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    courier_tracking: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    # Snapshot name+price at order time so edits later don't rewrite history
    product_name: Mapped[str] = mapped_column(String(200))
    price: Mapped[float] = mapped_column(Float)
    qty: Mapped[int] = mapped_column(Integer, default=1)

    order: Mapped["Order"] = relationship(back_populates="items")


class Settings(Base):
    """Single row (id=1): white-label branding + shop config.
    Super admin edits these; the React storefront reads them live."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Branding
    brand_name: Mapped[str] = mapped_column(String(100), default="AuraBD")
    tagline: Mapped[Optional[str]] = mapped_column(String(200), default="Modern Lifestyle Store")
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(20), default="#10b981")
    # Flash sale deal message shown in the announcement bar
    flash_sale_message: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    brand_blurb: Mapped[Optional[str]] = mapped_column(
        String(500),
        default="সাশ্রয়ী দামে অরিজিনাল পণ্য, সারা বাংলাদেশে ক্যাশ অন ডেলিভারি। আপনার বিশ্বস্ত অনলাইন শপ।",
    )
    # Contact & social (shown in the storefront footer)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    contact_address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    facebook_url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # Delivery
    delivery_inside: Mapped[float] = mapped_column(Float, default=60)
    delivery_outside: Mapped[float] = mapped_column(Float, default=120)
    free_delivery_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Integrations (super admin only, never exposed publicly)
    courier_provider: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # pathao|steadfast
    courier_api_key: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    courier_secret_key: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)  # steadfast needs both
    sms_api_key: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    sms_sender_id: Mapped[Optional[str]] = mapped_column(String(11), nullable=True)
    sms_api_url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    # SMS confirmation message template. Placeholders: {brand} {id} {items} {total}
    sms_confirmation_template: Mapped[str] = mapped_column(
        Text,
        default="{brand}: আপনার অর্ডার #{id} কনফার্ম হয়েছে।\n{items}\nমোট: ৳{total:,.0f} (ক্যাশ অন ডেলিভারি)\nশীঘ্রই ডেলিভারি দেওয়া হবে।",
    )
    facebook_pixel: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    facebook_access_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Store toggles
    store_open: Mapped[bool] = mapped_column(Boolean, default=True)
    # Custom checkout fields
    field_district: Mapped[bool] = mapped_column(Boolean, default=True)
    field_note: Mapped[bool] = mapped_column(Boolean, default=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Page(Base):
    """Editable static page (About Us, Contact, FAQ). Super admin edits these;
    the storefront renders them at /page/:slug."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Review(Base):
    """Product review. Public can post; admin approves (approved=False default)."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    rating: Mapped[int] = mapped_column(Integer)  # 1-5
    text: Mapped[str] = mapped_column(Text, default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Faq(Base):
    """Frequently asked questions — admin editable, shown on /faq."""

    __tablename__ = "faqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(String(300))
    answer: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Coupon(Base):
    """Discount code applied at checkout. code stored uppercase."""

    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(10), default="percent")  # percent | fixed
    value: Mapped[float] = mapped_column(Float)
    min_order: Mapped[float] = mapped_column(Float, default=0)
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
