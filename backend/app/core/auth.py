import json
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_db
from app.core.demo import DEMO_UID
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


# The demo session may read everything but write nothing, except asking the assistant
DEMO_READ_METHODS = {"GET", "HEAD", "OPTIONS"}
DEMO_WRITES_ALLOWED = {("POST", "/api/chat")}
DEMO_READ_ONLY = "You're viewing the demo, which is read-only. Sign up to track your own money."


def _demo_user(request: Request, token: str, db: Session) -> User:
    from app.services import demo
    session_id = demo.read_token(token)
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="The demo session has expired.")
    if request.method not in DEMO_READ_METHODS and (request.method, request.url.path.rstrip("/")) not in DEMO_WRITES_ALLOWED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DEMO_READ_ONLY)
    user = demo.demo_user(db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The demo is being reset. Try again in a minute.")
    user.demo_session = session_id      # per-visitor chat limits (services/chat.py)
    return user


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency — extracts Bearer token, verifies it with Firebase,
    then returns the matching User row from our DB (creates one if first login).
    A server-issued demo token ("demo.…") instead gives the shared read-only demo user.
    """
    token = credentials.credentials
    if token.startswith("demo."):
        return _demo_user(request, token, db)
    payload = verify_firebase_token(token)

    firebase_uid = payload["uid"]
    if firebase_uid == DEMO_UID:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
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