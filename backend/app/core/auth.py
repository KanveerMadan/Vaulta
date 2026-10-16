import json
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_db
from app.core.demo import DEMO_UID
from app.core.scope import bind_user, find_user
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


SIGNED_OUT = "Your session was signed out. Sign in again."


def verify_firebase_token(token: str, check_revoked: bool = False) -> dict:
    """
    Verify a Firebase ID token and return the decoded payload. With check_revoked, also ask Firebase whether the
    user's sessions were revoked (signed out everywhere, password changed) or the account disabled: one extra call,
    made on sensitive routes only (get_sensitive_user).
    """
    try:
        return firebase_auth.verify_id_token(token, check_revoked=check_revoked)
    except (firebase_auth.RevokedIdTokenError, firebase_auth.UserDisabledError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIGNED_OUT)
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
    bind_user(db, user)
    return user


# Failed sign-ins (bad, expired or forged tokens) per client IP before answering 429
BAD_TOKENS_PER_IP, BAD_TOKEN_WINDOW = 30, 600


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
    return _authenticate(request, credentials.credentials, db, check_revoked=False)


def get_sensitive_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """get_current_user, plus a revocation check with Firebase: for delete, export, unlink, settings changes."""
    return _authenticate(request, credentials.credentials, db, check_revoked=True)


def _authenticate(request: Request, token: str, db: Session, check_revoked: bool) -> User:
    from app.core import ratelimit
    try:
        return _user_for_token(request, token, db, check_revoked)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            ratelimit.check("bad-token", ratelimit.client_ip(request), BAD_TOKENS_PER_IP, BAD_TOKEN_WINDOW)
        raise


def _user_for_token(request: Request, token: str, db: Session, check_revoked: bool) -> User:
    if token.startswith("demo."):
        return _demo_user(request, token, db)
    payload = verify_firebase_token(token, check_revoked=check_revoked)

    firebase_uid = payload["uid"]
    if firebase_uid == DEMO_UID:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    email = payload.get("email", "")
    name = payload.get("name", "")

    # Upsert — create user on first login. The app fires several requests at once on a first
    # sign-in, so another request may create the row first: then use that one.
    user = find_user(db, "firebase_uid", firebase_uid)
    if not user:
        user = User(firebase_uid=firebase_uid, email=email, full_name=name)
        bind_user(db, user)             # gives the new user an id and a data key
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = find_user(db, "firebase_uid", firebase_uid)
            if user is None:
                raise
        db.refresh(user)

    bind_user(db, user)
    _note_sign_in(db, user, payload.get("auth_time"))
    if db.is_modified(user) or db.new:  # a data key was just created, or a sign-in recorded
        db.commit()
    return user


def _note_sign_in(db: Session, user: User, auth_time) -> None:
    """A token from a newer Firebase sign-in than the last one seen: record it in the activity log."""
    from app.services.activity import record
    if not isinstance(auth_time, (int, float)):
        return
    signed_in = datetime.fromtimestamp(auth_time, tz=timezone.utc)
    if user.last_sign_in_at is None or signed_in > user.last_sign_in_at:
        user.last_sign_in_at = signed_in
        record(db, user, "sign_in")
