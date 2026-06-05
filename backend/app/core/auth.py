import json
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User

settings = get_settings()
bearer_scheme = HTTPBearer()

# Initialise Firebase Admin SDK once at startup
def init_firebase():
    if not firebase_admin._apps:
        service_account = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
        cred = credentials.Certificate(service_account)
        firebase_admin.initialize_app(cred)

init_firebase()


def verify_firebase_token(token: str) -> dict:
    """Verify a Firebase ID token and return the decoded payload."""
    try:
        decoded = firebase_auth.verify_id_token(token)
        return decoded
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency — extracts Bearer token, verifies it with Firebase,
    then returns the matching User row from our DB (creates one if first login).
    """
    token = credentials.credentials
    payload = verify_firebase_token(token)

    firebase_uid = payload["uid"]
    email = payload.get("email", "")
    name = payload.get("name", "")

    # Upsert — create user on first login
    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
    if not user:
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            full_name=name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user