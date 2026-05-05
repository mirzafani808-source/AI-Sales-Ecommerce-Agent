"""
AI Sales Agent — One-time setup script for VS Code / local development.

Run this once before starting the app:
    python setup.py
"""
import os
import sys
import subprocess
import secrets

print("=" * 55)
print("   AI Sales Agent — Local Setup")
print("=" * 55)

# 1. Check Python version
py = sys.version_info
if py.major < 3 or py.minor < 9:
    print(f"ERROR: Python 3.9+ required (you have {py.major}.{py.minor})")
    sys.exit(1)
print(f"[OK] Python {py.major}.{py.minor}.{py.micro}")

# 2. Install dependencies
print("\n[...] Installing dependencies (this may take a minute)...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
    capture_output=True, text=True
)
if result.returncode != 0:
    print(f"[ERROR] pip install failed:\n{result.stderr}")
    sys.exit(1)
print("[OK] All packages installed")

# 3. Create .env if not present
if not os.path.exists(".env"):
    secret = secrets.token_hex(32)
    with open(".env", "w") as f:
        f.write(f"SESSION_SECRET={secret}\n")
        f.write("\n")
        f.write("# DATABASE_URL=postgresql://user:pass@localhost:5432/ai_sales\n")
        f.write("# GROQ_API_KEY=your-groq-key-here\n")
        f.write("\n")
        f.write("# --- Email (Gmail SMTP) ---\n")
        f.write("# SMTP_HOST=smtp.gmail.com\n")
        f.write("# SMTP_PORT=587\n")
        f.write("# SMTP_USE_TLS=true\n")
        f.write("# SMTP_USER=your-gmail@gmail.com\n")
        f.write("# SMTP_PASS=xxxx xxxx xxxx xxxx\n")
        f.write("# SMTP_FROM=your-gmail@gmail.com\n")
        f.write("# OWNER_EMAIL=your-gmail@gmail.com\n")
    print("[OK] .env file created (SESSION_SECRET auto-generated)")
    print()
    print("  *** IMPORTANT: To enable email notifications ***")
    print("  Edit .env and uncomment + fill in the SMTP_ lines.")
    print("  See .env.example for detailed Gmail setup instructions.")
else:
    print("[OK] .env already exists")

# 4. Create instance directory for SQLite
os.makedirs("instance", exist_ok=True)
print("[OK] instance/ directory ready")

# 5. Done
print()
print("=" * 55)
print("  Setup complete!")
print()
print("  Start the app:  python main.py")
print("  Open browser:   http://localhost:5000")
print()
print("  NOTE: The FIRST user who registers becomes Admin.")
print("=" * 55)
