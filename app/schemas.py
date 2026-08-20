from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------- Products ----------
class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: float
    original_price: Optional[float] = None
    image: str
    gallery: Optional[list] = []
    category: str
    stock: int
    badge: Optional[str] = None
    description: Optional[str] = None
    active: bool
    created_at: datetime
    # Filled in by the router from approved reviews
    avg_rating: Optional[float] = None
    review_count: int = 0


class ProductIn(BaseModel):
    name: str
    price: float
    original_price: Optional[float] = None
    image: str = ""
    gallery: Optional[list] = []
    category: str = "general"
    stock: int = 0
    badge: Optional[str] = None
    description: Optional[str] = None
    active: bool = True


# ---------- Orders ----------
class OrderItemIn(BaseModel):
    product_id: int
    qty: int = 1


class OrderIn(BaseModel):
    name: str
    phone: str
    address: str
    district: Optional[str] = None
    note: Optional[str] = None
    coupon_code: Optional[str] = None
    items: list[OrderItemIn]


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    price: float
    qty: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    address: str
    district: Optional[str] = None
    note: Optional[str] = None
    subtotal: float
    delivery_charge: float
    discount: float = 0
    coupon_code: Optional[str] = None
    total: float
    status: str
    payment: str
    courier_id: Optional[str] = None
    courier_tracking: Optional[str] = None
    created_at: datetime
    items: list[OrderItemOut] = []


class OrderTrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    total: float
    courier_tracking: Optional[str] = None
    created_at: datetime


class CourierStatusOut(BaseModel):
    provider: str = ""
    courier_id: Optional[str] = None
    courier_tracking: Optional[str] = None
    delivery_status: Optional[str] = None
    detail: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: str
    courier_tracking: Optional[str] = None
    # Admin may correct recipient details / shipping location
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    district: Optional[str] = None


# ---------- Auth ----------
class CustomerRegister(BaseModel):
    name: str
    phone: str
    password: str
    address: Optional[str] = None
    district: Optional[str] = None


class CustomerLogin(BaseModel):
    phone: str
    password: str


class AdminLogin(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    address: Optional[str] = None
    district: Optional[str] = None


class CustomerProfileUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    district: Optional[str] = None


class AdminUserCreate(BaseModel):
    username: str
    password: str
    role: str = "admin"  # admin or superadmin


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    created_at: datetime


# ---------- Settings ----------
class SettingsPublic(BaseModel):
    """Safe to expose to the storefront — no API keys."""

    model_config = ConfigDict(from_attributes=True)

    brand_name: str
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: str
    flash_sale_message: Optional[str] = None
    brand_blurb: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_address: Optional[str] = None
    facebook_url: Optional[str] = None
    whatsapp_number: Optional[str] = None
    delivery_inside: float
    delivery_outside: float
    free_delivery_threshold: Optional[float] = None
    store_open: bool
    field_district: bool
    field_note: bool
    # Pixel ID is not secret — the storefront must embed it; keep keys out.
    facebook_pixel: Optional[str] = None


class SettingsUpdate(BaseModel):
    brand_name: Optional[str] = None
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    flash_sale_message: Optional[str] = None
    brand_blurb: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_address: Optional[str] = None
    facebook_url: Optional[str] = None
    whatsapp_number: Optional[str] = None
    delivery_inside: Optional[float] = None
    delivery_outside: Optional[float] = None
    free_delivery_threshold: Optional[float] = None
    courier_provider: Optional[str] = None
    courier_api_key: Optional[str] = None
    courier_secret_key: Optional[str] = None
    sms_api_key: Optional[str] = None
    sms_sender_id: Optional[str] = None
    sms_api_url: Optional[str] = None
    sms_confirmation_template: Optional[str] = None
    facebook_pixel: Optional[str] = None
    facebook_access_token: Optional[str] = None
    store_open: Optional[bool] = None
    field_district: Optional[bool] = None
    field_note: Optional[bool] = None


class SettingsFull(SettingsPublic):
    courier_provider: Optional[str] = None
    courier_api_key: Optional[str] = None
    courier_secret_key: Optional[str] = None
    sms_api_key: Optional[str] = None
    sms_sender_id: Optional[str] = None
    sms_api_url: Optional[str] = None
    sms_confirmation_template: Optional[str] = None
    facebook_pixel: Optional[str] = None
    facebook_access_token: Optional[str] = None


# ---------- Pages ----------
class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    content: str
    active: bool
    updated_at: datetime


class PageUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    active: Optional[bool] = None


# ---------- FAQ ----------
class FaqOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer: str
    sort_order: int
    active: bool


class FaqIn(BaseModel):
    question: str
    answer: str
    sort_order: int = 0
    active: bool = True


# ---------- Reviews ----------
class ReviewIn(BaseModel):
    name: str
    rating: int
    text: str = ""


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    name: str
    rating: int
    text: str
    approved: bool
    created_at: datetime


class AdminReviewOut(ReviewOut):
    product_name: str = ""


# ---------- Coupons ----------
class CouponIn(BaseModel):
    code: str
    type: str = "percent"  # percent | fixed
    value: float
    min_order: float = 0
    max_uses: Optional[int] = None
    expires_at: Optional[datetime] = None
    active: bool = True


class CouponOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    type: str
    value: float
    min_order: float
    max_uses: Optional[int] = None
    used_count: int
    expires_at: Optional[datetime] = None
    active: bool
    created_at: datetime


class CouponValidateIn(BaseModel):
    code: str
    subtotal: float


class CouponValidateOut(BaseModel):
    code: str
    discount: float
    message: str


# ---------- Dashboard ----------
class DashboardOut(BaseModel):
    orders_today: int
    revenue_today: float
    pending_orders: int
    total_products: int
    low_stock_products: int


# ---------- Reports ----------
class DailySales(BaseModel):
    date: str  # YYYY-MM-DD
    orders: int
    revenue: float


class TopProduct(BaseModel):
    product_id: int
    product_name: str
    qty_sold: int
    revenue: float


class ReportOut(BaseModel):
    total_orders: int
    total_revenue: float
    total_delivery_charge: float
    total_discount: float
    cancelled_orders: int
    daily_sales: list[DailySales]
    top_products: list[TopProduct]
