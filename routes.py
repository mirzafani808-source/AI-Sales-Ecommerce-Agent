"""All HTTP routes for the AI Sales Agent ecommerce app."""
import os
import re
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    render_template, request, jsonify, redirect, url_for,
    flash, session, abort,
)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app import app, db, google, github
from models import User, Product, Order, OrderItem, ChatMessage, ContactMessage
from mailer import send_order_confirmation, send_contact_message, OWNER_EMAILS
from ml_models import FraudDetector, RecommendationEngine, SentimentAnalyzer


# -----------------------------------------------------------------------------
# ML / LLM init (lazy loaded)
# -----------------------------------------------------------------------------
_fraud_detector = None
_recommender = None
_sentiment_analyzer = None
_llm = None


def get_fraud_detector():
    global _fraud_detector
    if _fraud_detector is None:
        print("Loading Fraud Detector...")
        _fraud_detector = FraudDetector()
    return _fraud_detector


def get_recommender():
    global _recommender
    if _recommender is None:
        print("Loading Recommender...")
        _recommender = RecommendationEngine()
    return _recommender


def get_sentiment_analyzer():
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        print("Loading Sentiment Analyzer...")
        _sentiment_analyzer = SentimentAnalyzer()
    return _sentiment_analyzer


def get_llm():
    global _llm
    if _llm is not None:
        return _llm
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from langchain_groq import ChatGroq
        _llm = ChatGroq(api_key=api_key, model="llama-3.3-70b-versatile")
        print("Groq LLM ready")
    except Exception as e:
        print(f"Groq LLM init failed: {e}")
        _llm = None
    return _llm


SYSTEM_PROMPT = (
    "You are a friendly, helpful AI Sales Agent for an online ecommerce store. "
    "Help customers with products, prices, orders, shipping, returns and recommendations. "
    "Be concise (2-4 sentences), warm, and professional. "
    "If the customer mentions a product, suggest related items naturally. "
    "If asked about something outside ecommerce, politely steer back to shopping."
)

PRODUCT_KEYWORDS = [
    "laptop", "phone", "mouse", "keyboard", "headphones", "shirt",
    "shoes", "watch", "bag", "perfume",
]
SUSPICIOUS_KEYWORDS_RE = re.compile(
    r"\b(stolen|hack|fake card|carded|test card|chargeback|fraud)\b", re.I
)
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
DELIVERY_FEE = 5.99


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
@app.before_request
def make_session_permanent():
    session.permanent = True


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def get_cart():
    return session.setdefault("cart", {})


def cart_summary():
    cart = get_cart()
    if not cart:
        return [], 0.0, 0.0, 0.0, 0
    products = Product.query.filter(Product.id.in_([int(k) for k in cart.keys()])).all()
    items, subtotal, count = [], 0.0, 0
    for p in products:
        qty = int(cart.get(str(p.id), 0))
        if qty <= 0:
            continue
        line_total = p.price * qty
        items.append({"product": p, "qty": qty, "line_total": line_total})
        subtotal += line_total
        count += qty
    delivery = DELIVERY_FEE if subtotal > 0 else 0.0
    total = subtotal + delivery
    return items, subtotal, delivery, total, count


@app.context_processor
def inject_globals():
    _, _, _, _, count = cart_summary()
    unread_inbox = 0
    if current_user.is_authenticated and getattr(current_user, "is_admin", False):
        try:
            unread_inbox = ContactMessage.query.filter_by(is_read=False).count()
        except Exception:
            pass
    return {"cart_count": count, "unread_inbox": unread_inbox}


def extract_product(text):
    text_l = text.lower()
    for p in PRODUCT_KEYWORDS:
        if p in text_l:
            return p
    return None


def extract_amount(text):
    m = re.search(r"(?:\$|rs\.?|pkr|usd)?\s?(\d{2,7})", text.lower())
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return 0.0
    return 0.0


def fallback_response(message, product, sentiment):
    if product:
        recs = get_recommender().recommend(product)
        rec_text = ", ".join(recs[:3]) if recs else "some great related items"
        return (
            f"Great choice! We have a wide range of {product}s. "
            f"Customers also love: {rec_text}. Want to see prices or place an order?"
        )
    msg_l = message.lower()
    if any(w in msg_l for w in ["price", "cost", "kitne", "kitna"]):
        return "Prices vary by model. Tell me which product you're interested in and I'll share details."
    if any(w in msg_l for w in ["track", "order", "shipping"]):
        return "Sure — please share your order ID and I'll check the status for you."
    if any(w in msg_l for w in ["hello", "hi", "salam", "hey"]):
        return "Hi there! I'm your AI Sales Agent. What can I help you find today?"
    if sentiment == "NEGATIVE":
        return "I'm sorry to hear that. Could you share more details so I can help resolve it?"
    return "I'm here to help with products, prices, orders or recommendations. What would you like to know?"


# -----------------------------------------------------------------------------
# Public / landing routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    """Landing → if logged in show chat; else go to login."""
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    return render_template("index.html")


@app.route("/welcome")
def login_choice():
    return redirect(url_for("login"))


@app.route("/features")
def features():
    return render_template("features.html")


@app.route("/how-it-works")
def how_it_works():
    return render_template("how-it-works.html")


@app.route("/about")
def about():
    return render_template("about.html")


# -----------------------------------------------------------------------------
# Email/password auth
# -----------------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "error")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists. Please login.", "error")
            return redirect(url_for("login"))

        # Owner emails and first user always become admin
        is_first_user = User.query.count() == 0
        is_owner_email = email.lower() in [e.lower() for e in OWNER_EMAILS]
        u = User()
        u.id = str(uuid.uuid4())
        u.email = email
        first = name.split(" ")[0] if name else None
        last = " ".join(name.split(" ")[1:]) if name and len(name.split(" ")) > 1 else None
        u.first_name = first
        u.last_name = last
        u.is_admin = is_first_user or is_owner_email
        u.set_password(password)
        db.session.add(u)
        db.session.commit()

        flash("Account created — please log in to continue.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))
        login_user(user)
        flash(f"Welcome back, {user.display_name}!", "success")
        nxt = request.args.get("next") or url_for("index")
        return redirect(nxt)

    return render_template("login.html")


@app.route("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/auth/social/<provider>")
def social_login(provider):
    """Placeholder for Google/GitHub OAuth — wire it up by adding your own
    OAuth client id/secret and replacing this handler with Flask-Dance or
    Authlib. For now we just nudge the user toward email/password."""
    pretty = {"google": "Google", "github": "GitHub"}.get(provider.lower(), provider)
    flash(
        f"{pretty} login isn't configured yet — please use email & password for now. "
        f"(Add your {pretty} OAuth credentials to enable it.)",
        "info",
    )
    return redirect(url_for("login"))


# OAuth login handlers
@app.route("/auth/google")
def google_login():
    if google is None:
        flash("Google login is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.", "error")
        return redirect(url_for("login"))
    if not google.authorized:
        return redirect(url_for("google.login"))
    resp = google.get("/oauth2/v2/userinfo")
    user_info = resp.json()
    email = user_info.get("email")
    if not email:
        flash("Could not get email from Google.", "error")
        return redirect(url_for("login"))
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User()
        user.id = str(uuid.uuid4())
        user.email = email
        user.first_name = user_info.get("given_name", "")
        user.last_name = user_info.get("family_name", "")
        user.is_admin = email.lower() in [e.lower() for e in OWNER_EMAILS]
        user.set_password(str(uuid.uuid4()))  # random password
        db.session.add(user)
        db.session.commit()
    login_user(user)
    flash(f"Welcome, {user.display_name}!", "success")
    return redirect(url_for("index"))


@app.route("/auth/github")
def github_login():
    if github is None:
        flash("GitHub login is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.", "error")
        return redirect(url_for("login"))
    if not github.authorized:
        return redirect(url_for("github.login"))
    # Get user info
    resp = github.get("/user")
    user_info = resp.json()
    # Get email
    email_resp = github.get("/user/emails")
    emails = email_resp.json()
    primary_email = next((e["email"] for e in emails if e.get("primary")), None)
    if not primary_email:
        flash("Could not get email from GitHub.", "error")
        return redirect(url_for("login"))
    user = User.query.filter_by(email=primary_email).first()
    if not user:
        user = User()
        user.id = str(uuid.uuid4())
        user.email = primary_email
        user.first_name = user_info.get("name", "").split(" ")[0]
        user.last_name = " ".join(user_info.get("name", "").split(" ")[1:])
        user.is_admin = primary_email.lower() in [e.lower() for e in OWNER_EMAILS]
        user.set_password(str(uuid.uuid4()))  # random password
        db.session.add(user)
        db.session.commit()
    login_user(user)
    flash(f"Welcome, {user.display_name}!", "success")
    return redirect(url_for("index"))


# -----------------------------------------------------------------------------
# Products
# -----------------------------------------------------------------------------
@app.route("/products")
def products():
    category = request.args.get("category")
    q = Product.query.filter_by(is_active=True)
    if category:
        q = q.filter_by(category=category)
    items = q.order_by(Product.created_at.desc()).all()
    categories = [c[0] for c in db.session.query(Product.category).distinct().all() if c[0]]
    return render_template("products.html", products=items, categories=categories, current_category=category)


@app.route("/products/<int:pid>")
def product_detail(pid):
    p = Product.query.get_or_404(pid)
    related = Product.query.filter(Product.category == p.category, Product.id != p.id, Product.is_active == True).limit(4).all()
    return render_template("product_detail.html", product=p, related=related)


# -----------------------------------------------------------------------------
# Cart
# -----------------------------------------------------------------------------
@app.route("/cart")
def cart_view():
    items, subtotal, delivery, total, _ = cart_summary()
    return render_template("cart.html", items=items, subtotal=subtotal, delivery=delivery, total=total, delivery_fee=DELIVERY_FEE)


@app.route("/cart/add/<int:pid>", methods=["POST"])
def cart_add(pid):
    qty = max(1, int(request.form.get("qty", 1)))
    cart = get_cart()
    cart[str(pid)] = cart.get(str(pid), 0) + qty
    session["cart"] = cart
    flash("Added to cart.", "success")
    if request.headers.get("X-Requested-With") == "fetch":
        _, _, _, _, count = cart_summary()
        return jsonify({"ok": True, "count": count})
    return redirect(request.referrer or url_for("products"))


@app.route("/cart/update/<int:pid>", methods=["POST"])
def cart_update(pid):
    qty = max(0, int(request.form.get("qty", 1)))
    cart = get_cart()
    if qty == 0:
        cart.pop(str(pid), None)
    else:
        cart[str(pid)] = qty
    session["cart"] = cart
    return redirect(url_for("cart_view"))


@app.route("/cart/remove/<int:pid>", methods=["POST"])
def cart_remove(pid):
    cart = get_cart()
    cart.pop(str(pid), None)
    session["cart"] = cart
    return redirect(url_for("cart_view"))


@app.route("/cart/clear", methods=["POST"])
def cart_clear():
    session["cart"] = {}
    return redirect(url_for("cart_view"))


# -----------------------------------------------------------------------------
# Checkout
# -----------------------------------------------------------------------------
@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    items, subtotal, delivery, total, count = cart_summary()
    if count == 0:
        flash("Your cart is empty.", "error")
        return redirect(url_for("products"))

    if request.method == "POST":
        name = (request.form.get("name") or current_user.display_name or "").strip()
        email = (request.form.get("email") or current_user.email or "").strip()
        phone = (request.form.get("phone") or "").strip()
        address = (request.form.get("address") or "").strip()

        if not name or not email or not address:
            flash("Name, email and address are required.", "error")
            return redirect(url_for("checkout"))

        fraud_score = get_fraud_detector().predict(
            amount=total,
            items_count=count,
            suspicious_keywords=0,
            is_new_user=0 if current_user.is_authenticated else 1,
            is_rush_hour=0,
        )

        order = Order()
        order.user_id = current_user.id
        order.customer_name = name
        order.customer_email = email
        order.customer_phone = phone
        order.customer_address = address
        order.subtotal = round(subtotal, 2)
        order.delivery_fee = round(delivery, 2)
        order.total = round(total, 2)
        order.status = "Confirmed"
        order.fraud_score = round(float(fraud_score), 2)

        for it in items:
            p = it["product"]
            oi = OrderItem()
            oi.product_id = p.id
            oi.product_name = p.name
            oi.quantity = it["qty"]
            oi.price = p.price
            order.items.append(oi)
            p.stock = max(0, (p.stock or 0) - it["qty"])

        db.session.add(order)
        db.session.commit()

        email_status = "queued"
        try:
            res = send_order_confirmation(order, order.items)
            email_status = "sent" if res.get("sent") else f"skipped ({res.get('reason', 'no backend')})"
        except Exception as e:
            app.logger.warning(f"Email send failed: {e}")
            email_status = f"failed: {e}"

        session["cart"] = {}
        return render_template("order_success.html", order=order, email_status=email_status)

    return render_template(
        "checkout.html",
        items=items, subtotal=subtotal, delivery=delivery, total=total,
    )


# -----------------------------------------------------------------------------
# Admin: product management
# -----------------------------------------------------------------------------
@app.route("/admin/products", methods=["GET", "POST"])
@admin_required
def admin_products():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        try:
            price = float(request.form.get("price") or 0)
        except ValueError:
            price = 0
        try:
            cost_price = float(request.form.get("cost_price") or 0)
        except ValueError:
            cost_price = 0
        category = (request.form.get("category") or "").strip().lower() or None
        try:
            stock = int(request.form.get("stock") or 0)
        except ValueError:
            stock = 0

        image_url = (request.form.get("image_url") or "").strip() or None
        file = request.files.get("image_file")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in ALLOWED_IMAGE_EXT:
                flash("Image must be PNG, JPG, GIF or WebP.", "error")
                return redirect(url_for("admin_products"))
            fname = secure_filename(f"{uuid.uuid4().hex}.{ext}")
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))
            image_url = url_for("static", filename=f"uploads/{fname}")

        if not name or price <= 0:
            flash("Name and a positive price are required.", "error")
            return redirect(url_for("admin_products"))

        p = Product()
        p.name = name
        p.description = description
        p.price = price
        p.cost_price = cost_price
        p.category = category
        p.stock = stock
        p.image_url = image_url or "https://placehold.co/600x400/6366f1/ffffff?text=" + name.replace(" ", "+")
        p.is_active = True
        db.session.add(p)
        db.session.commit()
        flash(f"Product '{name}' added.", "success")
        return redirect(url_for("admin_products"))

    items = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin_products.html", products=items)


@app.route("/admin/products/<int:pid>/delete", methods=["POST"])
@admin_required
def admin_delete_product(pid):
    p = Product.query.get_or_404(pid)
    p.is_active = False
    db.session.commit()
    flash(f"Removed '{p.name}'.", "info")
    return redirect(url_for("admin_products"))


@app.route("/admin/products/<int:pid>/toggle", methods=["POST"])
@admin_required
def admin_toggle_product(pid):
    p = Product.query.get_or_404(pid)
    p.is_active = not p.is_active
    db.session.commit()
    return redirect(url_for("admin_products"))


# -----------------------------------------------------------------------------
# Owner Analytics — live charts (admin only)
# -----------------------------------------------------------------------------
@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    return render_template("admin_analytics.html")


@app.route("/api/admin/analytics")
@admin_required
def api_admin_analytics():
    days = max(1, min(60, int(request.args.get("days", 14))))
    since = datetime.utcnow() - timedelta(days=days)

    # Headline KPIs
    total_orders = db.session.query(func.count(Order.id)).scalar() or 0
    total_revenue = float(db.session.query(func.coalesce(func.sum(Order.total), 0.0)).scalar() or 0.0)
    avg_order = float(db.session.query(func.coalesce(func.avg(Order.total), 0.0)).scalar() or 0.0)
    total_customers = db.session.query(func.count(func.distinct(Order.customer_email))).scalar() or 0
    total_products = db.session.query(func.count(Product.id)).filter(Product.is_active == True).scalar() or 0

    # Profit/loss: revenue minus cost-of-goods. Cost falls back to 70% of price if unset.
    profit = 0.0
    cost_total = 0.0
    rows = (
        db.session.query(OrderItem, Product)
        .outerjoin(Product, Product.id == OrderItem.product_id)
        .all()
    )
    for oi, p in rows:
        line_revenue = (oi.price or 0) * (oi.quantity or 0)
        unit_cost = (p.cost_price if (p and p.cost_price and p.cost_price > 0) else (oi.price or 0) * 0.7)
        line_cost = unit_cost * (oi.quantity or 0)
        profit += line_revenue - line_cost
        cost_total += line_cost

    # Daily revenue + orders (last N days)
    daily = (
        db.session.query(
            func.date(Order.created_at).label("d"),
            func.coalesce(func.sum(Order.total), 0.0),
            func.count(Order.id),
        )
        .filter(Order.created_at >= since)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
        .all()
    )
    series_map = {str(d): (float(rev or 0), int(cnt or 0)) for d, rev, cnt in daily}
    labels, revenue_series, orders_series = [], [], []
    for i in range(days - 1, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).date().isoformat()
        labels.append(d[5:])  # MM-DD
        rev, cnt = series_map.get(d, (0.0, 0))
        revenue_series.append(round(rev, 2))
        orders_series.append(cnt)

    # Top selling products (units sold)
    top = (
        db.session.query(
            OrderItem.product_name,
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
            func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0.0).label("rev"),
        )
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(7)
        .all()
    )
    top_products = [
        {"name": n or "Unknown", "units": int(u or 0), "revenue": round(float(r or 0), 2)}
        for n, u, r in top
    ]

    # Order status breakdown
    status_rows = (
        db.session.query(Order.status, func.count(Order.id))
        .group_by(Order.status).all()
    )
    status_breakdown = {s or "Unknown": int(c or 0) for s, c in status_rows}

    # Category sales
    cat_rows = (
        db.session.query(
            Product.category,
            func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0.0).label("rev"),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .group_by(Product.category)
        .order_by(func.sum(OrderItem.price * OrderItem.quantity).desc())
        .all()
    )
    category_sales = [
        {"category": (c or "uncategorized").title(), "revenue": round(float(r or 0), 2)}
        for c, r in cat_rows
    ]

    # Recent orders
    recent = Order.query.order_by(Order.created_at.desc()).limit(8).all()
    recent_orders = [
        {
            "id": o.id,
            "customer": o.customer_name,
            "total": round(o.total, 2),
            "status": o.status,
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else None,
        }
        for o in recent
    ]

    return jsonify({
        "kpis": {
            "revenue": round(total_revenue, 2),
            "profit": round(profit, 2),
            "cost": round(cost_total, 2),
            "orders": total_orders,
            "avg_order": round(avg_order, 2),
            "customers": total_customers,
            "products": total_products,
            "margin_pct": round((profit / total_revenue * 100), 1) if total_revenue > 0 else 0,
        },
        "daily": {
            "labels": labels,
            "revenue": revenue_series,
            "orders": orders_series,
        },
        "top_products": top_products,
        "status_breakdown": status_breakdown,
        "category_sales": category_sales,
        "recent_orders": recent_orders,
    })


# -----------------------------------------------------------------------------
# Admin: Orders management
# -----------------------------------------------------------------------------
@app.route("/admin/orders")
@admin_required
def admin_orders():
    status_filter = request.args.get("status", "")
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20

    q = Order.query
    if status_filter:
        q = q.filter(Order.status == status_filter)
    orders = q.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    statuses = [s[0] for s in db.session.query(Order.status).distinct().all() if s[0]]
    return render_template("admin_orders.html", orders=orders, statuses=statuses, status_filter=status_filter)


@app.route("/admin/orders/<int:oid>/status", methods=["POST"])
@admin_required
def admin_update_order_status(oid):
    order = Order.query.get_or_404(oid)
    new_status = (request.form.get("status") or "").strip()
    if new_status:
        order.status = new_status
        db.session.commit()
        flash(f"Order #{oid} status updated to '{new_status}'.", "success")
    return redirect(request.referrer or url_for("admin_orders"))


# -----------------------------------------------------------------------------
# Contact page (public — for all visitors)
# -----------------------------------------------------------------------------
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        subject = (request.form.get("subject") or "").strip()
        message = (request.form.get("message") or "").strip()

        if not name or not email or not message:
            flash("Name, email and message are required.", "error")
            return redirect(url_for("contact"))

        # Save to DB (always works, even without SMTP)
        cm = ContactMessage()
        cm.name = name
        cm.email = email
        cm.subject = subject
        cm.message = message
        db.session.add(cm)
        db.session.commit()

        # Try to send email to owners
        try:
            send_contact_message(name, email, subject, message)
        except Exception as e:
            app.logger.warning(f"Contact email failed: {e}")

        flash("Your message has been sent! We'll get back to you soon.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html", owner_emails=OWNER_EMAILS)


# -----------------------------------------------------------------------------
# Admin: Contact inbox
# -----------------------------------------------------------------------------
@app.route("/admin/inbox")
@admin_required
def admin_inbox():
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    unread = sum(1 for m in messages if not m.is_read)
    # Mark all as read
    ContactMessage.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return render_template("admin_inbox.html", messages=messages, unread=unread)


@app.route("/admin/inbox/<int:mid>/delete", methods=["POST"])
@admin_required
def admin_inbox_delete(mid):
    cm = ContactMessage.query.get_or_404(mid)
    db.session.delete(cm)
    db.session.commit()
    flash("Message deleted.", "info")
    return redirect(url_for("admin_inbox"))


# -----------------------------------------------------------------------------
# Dashboard
# -----------------------------------------------------------------------------
@app.route("/dashboard")
@admin_required
def dashboard():
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    total_orders = db.session.query(func.count(Order.id)).scalar() or 0
    total_chats = db.session.query(func.count(ChatMessage.id)).scalar() or 0
    total_products = db.session.query(func.count(Product.id)).filter(Product.is_active == True).scalar() or 0
    avg_fraud = db.session.query(func.coalesce(func.avg(Order.fraud_score), 0.0)).scalar() or 0.0
    revenue = db.session.query(func.coalesce(func.sum(Order.total), 0.0)).scalar() or 0.0

    sentiment_counts = (
        db.session.query(ChatMessage.sentiment, func.count(ChatMessage.id))
        .group_by(ChatMessage.sentiment).all()
    )
    sentiments = {s or "NEUTRAL": c for s, c in sentiment_counts}

    return render_template(
        "dashboard.html",
        recent_orders=recent_orders,
        total_orders=total_orders,
        total_chats=total_chats,
        total_products=total_products,
        avg_fraud=round(float(avg_fraud), 2),
        revenue=round(float(revenue), 2),
        sentiments=sentiments,
    )


# -----------------------------------------------------------------------------
# Chat
# -----------------------------------------------------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"response": "Please type a message.", "sentiment": "NEUTRAL"}), 400

    sentiment = get_sentiment_analyzer().analyze(message)
    emoji = get_sentiment_analyzer().get_emoji(message)
    product = extract_product(message)

    recommendations = []
    if product:
        recommendations = get_recommender().recommend(product)

    amount = extract_amount(message)
    fraud_score = 0.0
    if amount >= 1000:
        fraud_score = get_fraud_detector().predict(
            amount=amount,
            items_count=1,
            suspicious_keywords=1 if SUSPICIOUS_KEYWORDS_RE.search(message) else 0,
            is_new_user=0 if current_user.is_authenticated else 1,
            is_rush_hour=0,
        )

    llm = get_llm()
    response_text = None
    if llm is not None:
        try:
            context = (
                f"Customer sentiment: {sentiment}.\n"
                f"Detected product: {product or 'none'}.\n"
                f"Suggested related items: {', '.join(recommendations) if recommendations else 'none'}.\n\n"
                f"Customer: {message}"
            )
            from langchain_core.messages import SystemMessage, HumanMessage
            res = llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=context),
            ])
            response_text = (res.content or "").strip()
        except Exception as e:
            print(f"LLM error: {e}")
            response_text = None

    if not response_text:
        response_text = fallback_response(message, product, sentiment)

    final_response = f"{emoji} {response_text}"

    try:
        msg = ChatMessage()
        msg.user_id = current_user.id if current_user.is_authenticated else None
        msg.user_message = message
        msg.bot_response = final_response
        msg.sentiment = sentiment
        db.session.add(msg)
        db.session.commit()
    except Exception as e:
        print(f"Chat log error: {e}")
        db.session.rollback()

    return jsonify({
        "response": final_response,
        "sentiment": sentiment,
        "recommendations": recommendations,
        "fraud_score": fraud_score,
        "product": product,
    })


# -----------------------------------------------------------------------------
# JSON API
# -----------------------------------------------------------------------------
@app.route("/api/orders")
def api_orders():
    orders = Order.query.order_by(Order.created_at.desc()).limit(20).all()
    return jsonify([
        {
            "id": o.id,
            "customer": o.customer_name,
            "total": o.total,
            "status": o.status,
            "fraud_score": o.fraud_score,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        } for o in orders
    ])


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "llm": get_llm() is not None,
        "fraud_model": get_fraud_detector().model is not None,
        "sentiment": get_sentiment_analyzer().analyzer is not None,
    })


# -----------------------------------------------------------------------------
# Seed sample products on first run
# -----------------------------------------------------------------------------
SEED_PRODUCTS = [
    {"name": "Dell XPS 13 Laptop", "description": "13-inch Ultrabook with Intel Core i7, 16GB RAM, 512GB SSD. Lightweight and powerful.",
     "price": 1299.00, "cost_price": 950.00, "category": "laptop", "stock": 12,
     "image_url": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600&q=80"},
    {"name": "MacBook Pro 14", "description": "Apple M3 chip, 16GB unified memory, 512GB SSD. Studio-grade performance.",
     "price": 1999.00, "cost_price": 1500.00, "category": "laptop", "stock": 8,
     "image_url": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=600&q=80"},
    {"name": "Logitech MX Master 3S", "description": "Wireless ergonomic mouse with quiet clicks and 8K DPI tracking.",
     "price": 99.00, "cost_price": 55.00, "category": "mouse", "stock": 45,
     "image_url": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=600&q=80"},
    {"name": "Mechanical Keyboard RGB", "description": "Hot-swappable mechanical keyboard with RGB backlight and tactile switches.",
     "price": 149.00, "cost_price": 80.00, "category": "keyboard", "stock": 30,
     "image_url": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=600&q=80"},
    {"name": "Sony WH-1000XM5 Headphones", "description": "Industry-leading noise cancellation, 30-hour battery life.",
     "price": 349.00, "cost_price": 220.00, "category": "headphones", "stock": 25,
     "image_url": "https://images.unsplash.com/photo-1583394838336-acd977736f90?w=600&q=80"},
    {"name": "iPhone 15 Pro", "description": "A17 Pro chip, titanium design, 48MP camera system. Latest flagship.",
     "price": 999.00, "cost_price": 720.00, "category": "phone", "stock": 18,
     "image_url": "https://images.unsplash.com/photo-1592750475338-74b7b21085ab?w=600&q=80"},
    {"name": "Cotton Polo T-Shirt", "description": "100% pima cotton polo shirt — multiple colors available.",
     "price": 39.00, "cost_price": 14.00, "category": "shirt", "stock": 100,
     "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=600&q=80"},
    {"name": "Classic White Sneakers", "description": "Minimalist leather sneakers — comfortable for daily wear.",
     "price": 89.00, "cost_price": 38.00, "category": "shoes", "stock": 60,
     "image_url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&q=80"},
    {"name": "Apple Watch Series 9", "description": "Health tracking, GPS, always-on Retina display. Aluminum case.",
     "price": 429.00, "cost_price": 300.00, "category": "watch", "stock": 22,
     "image_url": "https://images.unsplash.com/photo-1546868871-7041f2a55e12?w=600&q=80"},
    {"name": "Premium Leather Bag", "description": "Hand-crafted full-grain leather messenger bag — fits a 15-inch laptop.",
     "price": 189.00, "cost_price": 90.00, "category": "bag", "stock": 14,
     "image_url": "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=600&q=80"},
]


with app.app_context():
    if Product.query.count() == 0:
        for s in SEED_PRODUCTS:
            p = Product()
            for k, v in s.items():
                setattr(p, k, v)
            db.session.add(p)
        db.session.commit()
        app.logger.info(f"Seeded {len(SEED_PRODUCTS)} products")
