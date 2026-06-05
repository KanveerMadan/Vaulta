import sys
import traceback
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Test config load
try:
    from app.core.config import get_settings
    settings = get_settings()
    print("✓ Config loaded")
except Exception as e:
    print(f"✗ Config failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test database
try:
    from app.core.database import Base, engine
    Base.metadata.create_all(bind=engine)
    print("✓ Database connected")
except Exception as e:
    print(f"✗ Database failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test Firebase
try:
    from app.core.auth import init_firebase
    init_firebase()
    print("✓ Firebase initialised")
except Exception as e:
    print(f"✗ Firebase failed: {e}")
    traceback.print_exc()
    sys.exit(1)

from app.api.routes import auth

app = FastAPI(title="Vaulta API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok", "env": settings.ENVIRONMENT}