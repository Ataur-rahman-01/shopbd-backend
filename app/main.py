from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models
from .auth import hash_password
from .database import Base, SessionLocal, engine
from .routers import admin, auth_routes, coupons, faqs, orders, storefront, superadmin

# Starter catalog (matches the AuraBD glass template). Edit per client.
SAMPLE_PRODUCTS = [
    {"name": "Aura Pro Smartwatch Series 9", "category": "gadgets", "price": 3499, "original_price": 4999, "image": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&q=80&w=500", "badge": "Hot", "stock": 20},
    {"name": "Wireless Noise Cancelling Earbuds", "category": "gadgets", "price": 2199, "original_price": 3299, "image": "https://images.unsplash.com/photo-1590658268037-6bf12165a8df?auto=format&fit=crop&q=80&w=500", "badge": "Sale", "stock": 35},
    {"name": "Premium Cotton Casual Panjabi", "category": "fashion", "price": 1850, "original_price": 2500, "image": "https://images.unsplash.com/photo-1617137984095-74e4e5e3613f?auto=format&fit=crop&q=80&w=500", "badge": "Eid Special", "stock": 15},
    {"name": "Minimalist Ceramic Table Lamp", "category": "home", "price": 1450, "original_price": 2100, "image": "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?auto=format&fit=crop&q=80&w=500", "badge": "Trending", "stock": 12},
    {"name": "Organic Sundarban Honey (500g)", "category": "grocery", "price": 650, "original_price": 850, "image": "https://images.unsplash.com/photo-1587049352847-4a222e784d38?auto=format&fit=crop&q=80&w=500", "badge": "Pure", "stock": 50},
    {"name": "Hydrating Vitamin C Face Serum", "category": "beauty", "price": 990, "original_price": 1490, "image": "https://images.unsplash.com/photo-1620916566398-39f1143ab7be?auto=format&fit=crop&q=80&w=500", "badge": "Best Seller", "stock": 30},
    {"name": "Ergonomic Laptop Stand Aluminum", "category": "gadgets", "price": 1290, "original_price": 1800, "image": "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?auto=format&fit=crop&q=80&w=500", "badge": "New", "stock": 25},
    {"name": "Designer Oversized Hoodie", "category": "fashion", "price": 1750, "original_price": 2400, "image": "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?auto=format&fit=crop&q=80&w=500", "badge": "Hot", "stock": 18},
]


SAMPLE_PAGES = [
    {
        "slug": "about-us",
        "title": "আমাদের সম্পর্কে",
        "content": (
            "আমরা একটি আধুনিক অনলাইন শপ, যারা বাংলাদেশের যেকোনো প্রান্তে মানসম্মত পণ্য "
            "পৌঁছে দিই। আমাদের লক্ষ্য সহজ — সাশ্রয়ী দামে অরিজিনাল পণ্য, দ্রুত ডেলিভারি এবং "
            "নিশ্চিন্তে কেনাকাটার অভিজ্ঞতা।\n"
            "ক্যাশ অন ডেলিভারি, bKash, নগদ ও রকেট — সব জনপ্রিয় পেমেন্ট মাধ্যমেই অর্ডার করা যায়। "
            "সারা দেশে হোম ডেলিভারি, আর ঢাকার ভিতরে অর্ডার পৌঁছায় মাত্র ২৪–৪৮ ঘণ্টায়।\n"
            "যেকোনো প্রশ্নে আমাদের হটলাইনে কল করুন — আমরা সবসময় আপনার পাশে আছি।"
        ),
    },
    {
        "slug": "contact",
        "title": "যোগাযোগ",
        "content": (
            "আমাদের সাথে যোগাযোগ করতে পারেন:\n"
            "হটলাইন: ০১XXXXXXXXX (সকাল ৯টা – রাত ১০টা)\n"
            "ইমেইল: support@shopbd.com\n"
            "ঠিকানা: ঢাকা, বাংলাদেশ\n"
            "ফেসবুক পেজে মেসেজ করলেও দ্রুত উত্তর পাবেন।"
        ),
    },
    {
        "slug": "faq",
        "title": "সাধারণ প্রশ্নোত্তর",
        "content": (
            "প্রশ্ন: ডেলিভারি কত দিনে হয়?\n"
            "উত্তর: ঢাকার ভিতরে ২৪–৪৮ ঘণ্টা, ঢাকার বাইরে ২–৪ দিন।\n"
            "প্রশ্ন: পেমেন্ট কীভাবে করবো?\n"
            "উত্তর: ক্যাশ অন ডেলিভারি (COD), bKash, নগদ ও রকেট — যেকোনোটি বেছে নিতে পারবেন।\n"
            "প্রশ্ন: পণ্য ফেরত দেওয়া যাবে?\n"
            "উত্তর: হ্যাঁ, পণ্যে সমস্যা থাকলে ৭ দিনের মধ্যে রিটার্ন করতে পারবেন।"
        ),
    },
    {
        "slug": "return-policy",
        "title": "রিটার্ন পলিসি",
        "content": (
            "আমরা চাই আপনি প্রতিটি কেনাকাটায় সন্তুষ্ট থাকুন। তাই ডেলিভারির ৭ দিনের মধ্যে "
            "রিটার্নের সুযোগ আছে — তবে কিছু শর্ত মেনে।\n"
            "রিটার্নের শর্ত:\n"
            "• ডেলিভারির ৭ দিনের মধ্যে রিটার্নের আবেদন করতে হবে।\n"
            "• পণ্য অব্যবহৃত, অক্ষত ও অরিজিনাল প্যাকেজিংয়ে থাকতে হবে।\n"
            "• পণ্যের প্যাকেট খোলা বা ব্যবহার করা হলে রিটার্ন গ্রহণ করা হবে না।\n"
            "• রিটার্নের সময় অর্ডার নম্বর ও ফোন নম্বর জানাতে হবে।\n"
            "যেসব ক্ষেত্রে রিটার্ন গ্রহণযোগ্য নয়:\n"
            "• খোলা বা ব্যবহৃত পণ্য\n"
            "• অরিজিনাল প্যাকেজিং বা ট্যাগ ছাড়া পণ্য\n"
            "• ডেলিভারির ৭ দিন পরের আবেদন\n"
            "রিফান্ড প্রসেস:\n"
            "১. হটলাইনে কল করে রিটার্নের আবেদন করুন।\n"
            "২. পণ্য যাচাইয়ের পর আমরা কুরিয়ারে পণ্য ফেরত নেওয়ার ব্যবস্থা করবো।\n"
            "৩. পণ্য পেয়ে যাচাই শেষে ৩–৫ কর্মদিবসের মধ্যে রিফান্ড প্রসেস হবে।\n"
            "৪. COD অর্ডারের রিফান্ড আপনার পছন্দমতো bKash/নগদ/ব্যাংকে পাঠানো হবে।"
        ),
    },
    {
        "slug": "terms",
        "title": "শর্তাবলী",
        "content": (
            "আমাদের সাইট থেকে কেনাকাটা করলে নিচের শর্তগুলোতে আপনি সম্মত আছেন বলে ধরা হবে।\n"
            "অর্ডার কনফার্মেশন:\n"
            "• অর্ডার দেওয়ার পর আমাদের টিম ফোন কলে অর্ডার কনফার্ম করবে।\n"
            "• ফোনে কনফার্ম না হলে অর্ডার শিপ করা হবে না।\n"
            "• পরপর ৩ বার কল করেও না পেলে অর্ডার বাতিল বলে গণ্য হবে।\n"
            "অর্ডার বাতিল:\n"
            "• ভুল বা মিথ্যা তথ্য (নাম, ফোন, ঠিকানা) দিয়ে অর্ডার করলে আমরা অর্ডার বাতিল করার অধিকার রাখি।\n"
            "• পণ্য স্টকে না থাকলে ফোনে জানিয়ে অর্ডার বাতিল করা হবে।\n"
            "দাম ও অফার:\n"
            "• যেকোনো সময় পণ্যের দাম পরিবর্তনের অধিকার আমরা রাখি।\n"
            "• অফার ও ডিসকাউন্ট সীমিত সময়ের জন্য প্রযোজ্য।\n"
            "• ডেলিভারি চার্জ ঢাকার ভিতরে ও বাইরে আলাদা — চেকআউটে বিস্তারিত দেখানো হয়।"
        ),
    },
    {
        "slug": "privacy",
        "title": "প্রাইভেসি পলিসি",
        "content": (
            "আপনার ব্যক্তিগত তথ্য আমাদের কাছে গুরুত্বপূর্ণ। আমরা শুধু অর্ডার ডেলিভারির জন্য "
            "প্রয়োজনীয় তথ্যই সংগ্রহ করি।\n"
            "কী তথ্য সংগ্রহ করি:\n"
            "• নাম — ডেলিভারির সময় আপনার পরিচয়ের জন্য।\n"
            "• ফোন নম্বর — অর্ডার কনফার্মেশন ও ডেলিভারির জন্য।\n"
            "• ঠিকানা ও জেলা — পণ্য পৌঁছে দেওয়ার জন্য।\n"
            "কীভাবে ব্যবহার করি:\n"
            "• আপনার তথ্য শুধু অর্ডার প্রসেস ও ডেলিভারির কাজেই ব্যবহৃত হয়।\n"
            "• কোনো অবস্থাতেই আপনার তথ্য তৃতীয় পক্ষকে দেওয়া হয় না।\n"
            "• ফোন নম্বর শুধু অর্ডার সংক্রান্ত যোগাযোগে ব্যবহৃত হয় — মার্কেটিং স্প্যাম পাঠানো হয় না।\n"
            "নিরাপত্তা:\n"
            "• অর্ডারের তথ্য নিরাপদভাবে সংরক্ষণ করা হয়।\n"
            "• পেমেন্ট সম্পর্কিত কোনো তথ্য আমরা সংরক্ষণ করি না।"
        ),
    },
    {
        "slug": "delivery-info",
        "title": "ডেলিভারি তথ্য",
        "content": (
            "সারা বাংলাদেশে হোম ডেলিভারি। অর্ডার কনফার্ম হওয়ার পর আমাদের টিম ফোনে "
            "ডেলিভারির সময় জানিয়ে দেয়।\n"
            "ডেলিভারি সময় ও চার্জ:\n"
            "• ঢাকার ভিতরে: ৪৮ ঘন্টায় ডেলিভারি, চার্জ ৳{delivery_inside}\n"
            "• ঢাকার বাইরে: ৩-৫ কর্মদিবসে ডেলিভারি, চার্জ ৳{delivery_outside}\n"
            "• ৳{threshold}+ অর্ডারে ফ্রি ডেলিভারি — কোনো ডেলিভারি চার্জ দিতে হবে না।\n"
            "ক্যাশ অন ডেলিভারি (COD):\n"
            "আমাদের পেমেন্ট ব্যবস্থা ক্যাশ অন ডেলিভারি — অর্ডারের সময় কোনো টাকা দিতে হয় "
            "না। ডেলিভারি ম্যান পণ্য হাতে দিলে দেখে-শুনে টাকা দেবেন। পণ্য পছন্দ না হলে "
            "সেই মুহূর্তেই ফেরত দিতে পারবেন, কোনো প্রশ্ন করা হবে না।\n"
            "অন্যান্য তথ্য:\n"
            "• পাঠানোর আগে প্রতিটি পণ্য কোয়ালিটি চেক করা হয়।\n"
            "• ঢাকা শহরের ভিতরে ডেলিভারি ম্যান সরাসরি ঠিকানায় পৌঁছে দেয়।\n"
            "• কোনো সমস্যা হলে ডেলিভারির ৭ দিনের মধ্যে রিটার্ন করা যাবে।"
        ),
    },
]


SAMPLE_FAQS = [
    {
        "question": "ডেলিভারি কতদিনে হয়?",
        "answer": "ঢাকার ভিতরে অর্ডার ২৪-৪৮ ঘণ্টার মধ্যে পৌঁছে যায়। ঢাকার বাইরে ৩-৫ কর্মদিবস লাগে। অর্ডার কনফার্ম হওয়ার পর আমরা ফোনে ডেলিভারির সময় জানিয়ে দিই।",
        "sort_order": 1,
    },
    {
        "question": "ক্যাশ অন ডেলিভারি কীভাবে কাজ করে?",
        "answer": "খুব সহজ — আপনি অর্ডার করবেন, আমরা পণ্য পাঠাবো, আর পণ্য হাতে পেয়ে ডেলিভারি ম্যানকে টাকা দেবেন। আগে কোনো টাকা দিতে হবে না। পছন্দ না হলে সেই মুহূর্তেই ফেরত দিতে পারবেন।",
        "sort_order": 2,
    },
    {
        "question": "রিটার্ন পলিসি কী?",
        "answer": "পণ্যে কোনো সমস্যা থাকলে ডেলিভারির ৭ দিনের মধ্যে রিটার্ন করতে পারবেন। পণ্য অবশ্যই অব্যবহৃত ও অক্ষত অবস্থায় থাকতে হবে। বিস্তারিত জানতে হটলাইনে কল করুন।",
        "sort_order": 3,
    },
    {
        "question": "পেমেন্ট কীভাবে করব?",
        "answer": "এই মুহূর্তে ক্যাশ অন ডেলিভারি (COD) — পণ্য হাতে পেয়ে টাকা দিন। খুব শীঘ্রই বিকাশ, নগদ ও রকেট পেমেন্ট যুক্ত হচ্ছে।",
        "sort_order": 4,
    },
    {
        "question": "প্রোডাক্ট অরিজিনাল কিনা?",
        "answer": "আমরা ১০০% অরিজিনাল পণ্য দিই। প্রতিটি পণ্য যাচাই করে পাঠানো হয়। পণ্য অরিজিনাল না হলে সম্পূর্ণ টাকা ফেরত — এই আমাদের প্রতিশ্রুতি।",
        "sort_order": 5,
    },
    {
        "question": "অর্ডার ট্র্যাক করব কীভাবে?",
        "answer": "হোমপেজের 'ট্র্যাক' বাটনে ক্লিক করে অর্ডারের সময় দেওয়া মোবাইল নম্বর দিন — সব অর্ডারের বর্তমান অবস্থা দেখতে পাবেন। কোনো লগইন লাগবে না।",
        "sort_order": 6,
    },
]


def seed():
    db = SessionLocal()
    try:
        if not db.get(models.Settings, 1):
            db.add(models.Settings(id=1))
        if db.query(models.AdminUser).count() == 0:
            db.add(
                models.AdminUser(
                    username="admin",
                    password_hash=hash_password("admin123"),
                    role="superadmin",
                )
            )
        if db.query(models.Product).count() == 0:
            for p in SAMPLE_PRODUCTS:
                db.add(models.Product(**p))
        for pg in SAMPLE_PAGES:
            exists = db.query(models.Page).filter(models.Page.slug == pg["slug"]).first()
            if not exists:
                db.add(models.Page(**pg))
        if db.query(models.Faq).count() == 0:
            for f in SAMPLE_FAQS:
                db.add(models.Faq(**f))
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    # Lightweight migration: add `description` to existing DBs (create_all won't alter)
    from sqlalchemy import text

    with engine.begin() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(products)"))] if str(engine.url).startswith("sqlite") else []
        if not cols:  # Postgres path
            from sqlalchemy import inspect

            cols = [c["name"] for c in inspect(engine).get_columns("products")]
        if "description" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN description TEXT"))
        # Lightweight migration: gallery (extra product photos) on existing DBs
        if "gallery" not in cols:
            conn.execute(text("ALTER TABLE products ADD COLUMN gallery JSON"))
        # Lightweight migration: contact/social settings columns on existing DBs
        s_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(settings)"))] if str(engine.url).startswith("sqlite") else [c["name"] for c in inspect(engine).get_columns("settings")]
        for col, ddl in (
            ("brand_blurb", "ALTER TABLE settings ADD COLUMN brand_blurb VARCHAR(500) DEFAULT 'সাশ্রয়ী দামে অরিজিনাল পণ্য, সারা বাংলাদেশে ক্যাশ অন ডেলিভারি। আপনার বিশ্বস্ত অনলাইন শপ।'"),
            ("contact_phone", "ALTER TABLE settings ADD COLUMN contact_phone VARCHAR(30)"),
            ("flash_sale_message", "ALTER TABLE settings ADD COLUMN flash_sale_message VARCHAR(300)"),
            ("contact_address", "ALTER TABLE settings ADD COLUMN contact_address VARCHAR(300)"),
            ("facebook_url", "ALTER TABLE settings ADD COLUMN facebook_url VARCHAR(300)"),
            ("whatsapp_number", "ALTER TABLE settings ADD COLUMN whatsapp_number VARCHAR(30)"),
            ("facebook_access_token", "ALTER TABLE settings ADD COLUMN facebook_access_token VARCHAR(500)"),
            ( "courier_secret_key", "ALTER TABLE settings ADD COLUMN courier_secret_key VARCHAR(300)"),
                        ("sms_sender_id", "ALTER TABLE settings ADD COLUMN sms_sender_id VARCHAR(11)"),
                        ("sms_api_url", "ALTER TABLE settings ADD COLUMN sms_api_url VARCHAR(300)"),
                        ("sms_confirmation_template", "ALTER TABLE settings ADD COLUMN sms_confirmation_template TEXT"),
        ):
            if col not in s_cols:
                conn.execute(text(ddl))
        # Lightweight migration: coupon fields on orders for existing DBs
        o_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(orders)"))] if str(engine.url).startswith("sqlite") else [c["name"] for c in inspect(engine).get_columns("orders")]
        for col, ddl in (
            ("discount", "ALTER TABLE orders ADD COLUMN discount FLOAT DEFAULT 0"),
            ("coupon_code", "ALTER TABLE orders ADD COLUMN coupon_code VARCHAR(50)"),
        ):
            if col not in o_cols:
                conn.execute(text(ddl))
    seed()
    yield


app = FastAPI(title="ShopBD API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the client's domain in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve admin-uploaded images (logo, product photos) under /media.
# Same directory the admin upload endpoint writes to: backend/uploads/.
MEDIA_DIR = admin.UPLOAD_DIR
os.makedirs(MEDIA_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

app.include_router(storefront.router)
app.include_router(orders.router)
app.include_router(coupons.router)
app.include_router(auth_routes.router)
app.include_router(admin.router)
app.include_router(superadmin.router)
app.include_router(faqs.router)


@app.get("/")
def root():
    return {"app": "ShopBD white-label e-commerce API", "docs": "/docs"}
