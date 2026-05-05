# AI Sales Agent — Ecommerce

A Flask-based AI shopping assistant with products catalog, shopping cart,
checkout (with delivery fee), order management, fraud detection, sentiment
analysis, recommendations, **owner analytics dashboard with live charts**,
and email notifications on new orders.

## Quick start (VS Code / local)

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) copy the example env file and edit
cp .env.example .env

# 4. Run the app
python main.py
```

Then open <http://localhost:5000>.

The first user who registers automatically becomes the **owner / admin**
and gets the "Owner Analytics" and "Manage Products" pages in the sidebar.

## What's included

| Page | URL | Notes |
|---|---|---|
| Login / Register | `/login`, `/register` | Email + password (Google / GitHub buttons are placeholder — wire your own OAuth keys in `routes.py::social_login`) |
| AI Chat | `/` | Sales assistant chat (Groq LLaMA when `GROQ_API_KEY` is set, otherwise smart rule-based fallback) |
| Products catalog | `/products` | Pre-seeded with 10 sample products |
| Product detail | `/products/<id>` | Related items |
| Shopping cart | `/cart` | Add / update / remove / clear |
| Checkout | `/checkout` | Auth required, $5.99 delivery fee, fraud-score check, email notification |
| Customer dashboard | `/dashboard` | Personal stats + recent orders |
| **Owner Analytics** | `/admin/analytics` | **Live charts**: revenue trend, profit/loss, top products, category sales, status breakdown, recent orders. Auto-refreshes every 30 s. Admin only. |
| Manage products | `/admin/products` | Upload images, set price + cost (for accurate profit), toggle visibility. Admin only. |

## Configuration

All settings live in environment variables — see `.env.example` for the
full list. The most useful ones:

- `SESSION_SECRET` — required in production. Any long random string.
- `DATABASE_URL` — Postgres URL. If blank the app uses local SQLite.
- `GROQ_API_KEY` — optional. Free key from https://console.groq.com to
  enable LLM-powered chat. The app falls back to rule-based answers
  without it.
- `SMTP_HOST` / `SMTP_USER` / `SMTP_PASS` / `OWNER_EMAIL` — optional. If
  set, order-confirmation emails are sent to the owner via SMTP. On
  Replit, the built-in mailer is used automatically without setup.

## Project layout

```
.
├── main.py                  # entry point  (python main.py)
├── app.py                   # Flask app + DB + login manager
├── models.py                # SQLAlchemy models (User, Product, Order...)
├── routes.py                # All HTTP routes (auth, cart, checkout, analytics)
├── mailer.py                # Portable email helper (Replit Mail or SMTP)
├── ml_models.py             # FraudDetector, RecommendationEngine, SentimentAnalyzer
├── fraud_model.pkl          # Pre-trained fraud-detection model
├── recommendations.json     # Product recommendation seed data
├── requirements.txt
├── .env.example
├── templates/               # Jinja templates (base, login, products, ...)
│   └── admin_analytics.html # Owner dashboard with Chart.js
└── static/
    ├── css/style.css
    ├── js/main.js
    └── uploads/             # Admin-uploaded product images
```

## Tech

Backend: Flask, Flask-SQLAlchemy, Flask-Login, SQLAlchemy, Werkzeug.
ML: scikit-learn, joblib, numpy. AI chat: langchain-groq.
Frontend: vanilla HTML/CSS/JS + Chart.js for the analytics charts.

## Notes

- The "Continue with Google" / "Continue with GitHub" buttons on the
  login page are visual placeholders. To make them functional, register
  an OAuth app on Google / GitHub and replace `social_login` in
  `routes.py` with a `Flask-Dance` or `Authlib` integration.
- The Owner Analytics page treats `cost_price = 0` as "30% margin
  assumed" so profit numbers show up immediately. Set real cost prices
  in the Manage Products page for accurate figures.
