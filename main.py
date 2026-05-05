"""Entry point. Run with: python main.py"""
from app import app
import routes  # noqa: F401  registers routes onto `app`

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
