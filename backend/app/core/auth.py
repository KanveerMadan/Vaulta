import json
import time
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


class CodedError(HTTPException):
    """An error the web app acts on: the body is {"detail": message, "code": code} (handler in app/main.py)."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail=message)
        self.code = code


class TokenInfo:
    """What the ID token says about this sign-in (attached to the user for the request as user.token)."""

    def __init__(self, payload: dict):
        firebase = payload.get("firebase") or {}
        self.provider = firebase.get("sign_in_provider") or "unknown"     # password | google.com | …
        # Google sign-ins count as verified (Google owns the address); email/password sign-ups must click the link
        self.email_verified = bool(payload.get("email_verified")) or self.provider == "google.com"
        self.auth_time = payload.get("auth_time")       # when the user last actually signed in (seconds)
        self.issued_at = payload.get("iat")             # when this ID token was minted


# An unverified email/password account can sign in, see and answer onboarding, change its settings and delete
# itself, but nothing that creates data or reaches outside (imports, forwarding address, Telegram, chat).
UNVERIFIED_WRITES_ALLOWED = {
    ("PATCH", "/auth/me"), ("DELETE", "/auth/me"), ("PATCH", "/api/onboarding"), ("PATCH", "/api/settings"),
    ("POST", "/api/account/reauth-failed"),
}
UNVERIFIED_READS_BLOCKED = {("GET", "/api/inbound")}   # shows (and creates) the forwarding address
EMAIL_UNVERIFIED = "Verify your email address first: open the link we sent you, then try again."


def _route_key(request: Request) -> tuple[str, str]:
    route = request.scope.get("route")
    return request.method, getattr(route, "path", request.url.path.rstrip("/"))


def require_verified(request: Request, token: TokenInfo) -> None:
    method, path = _route_key(request)
    blocked = (
        (method not in DEMO_READ_METHODS and (method, path) not in UNVERIFIED_WRITES_ALLOWED)
        or (method, path) in UNVERIFIED_READS_BLOCKED)
    if not token.email_verified and blocked:
        raise CodedError(status.HTTP_403_FORBIDDEN, "email_unverified", EMAIL_UNVERIFIED)


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


REAUTH_REQUIRED = "For your security, sign in again to do this."


def get_recent_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    get_sensitive_user, plus: the user actually signed in (password or Google) within the last 5 minutes, by the
    token's auth_time. Otherwise 403 {code: reauth_required}; the web app asks them to sign in again and retries.
    For export, delete everything, password and sign-in method changes, address regeneration, Telegram unlink.
    """
    user = _authenticate(request, credentials.credentials, db, check_revoked=True)
    token = getattr(user, "token", None)
    if token is None:                     # the demo: read-only, and nothing personal to protect
        return user
    if not isinstance(token.auth_time, (int, float)) or time.time() - token.auth_time > settings.RECENT_LOGIN_SECONDS:
        raise CodedError(status.HTTP_403_FORBIDDEN, "reauth_required", REAUTH_REQUIRED)
    return user


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
    token_info = TokenInfo(payload)
    email = payload.get("email", "")
    name = payload.get("name", "")

    # Upsert — create user on first login. The app fires several requests at once on a first
    # sign-in, so another request may create the row first: then use that one.
    user = find_user(db, "firebase_uid", firebase_uid)
    if not user:
        from app.services.activity import record
        user = User(firebase_uid=firebase_uid, email=email, full_name=name)
        bind_user(db, user)             # gives the new user an id and a data key
        db.add(user)
        try:
            db.flush()                  # the user row first: the activity entry points at it
            record(db, user, "sign_up", {"method": token_info.provider})
            db.commit()
        except IntegrityError:
            db.rollback()
            user = find_user(db, "firebase_uid", firebase_uid)
            if user is None:
                raise
        db.refresh(user)

    bind_user(db, user)
    user.token = token_info
    _note_sign_in(db, user, token_info)
    if db.is_modified(user) or db.new:  # a data key was just created, or a sign-in recorded
        db.commit()
    require_verified(request, token_info)
    return user


def _note_sign_in(db: Session, user: User, token: TokenInfo) -> None:
    """A token from a newer Firebase sign-in than the last one seen: record it (and how) in the activity log."""
    from app.services.activity import record
    if not isinstance(token.auth_time, (int, float)):
        return
    signed_in = datetime.fromtimestamp(token.auth_time, tz=timezone.utc)
    if user.last_sign_in_at is None or signed_in > user.last_sign_in_at:
        user.last_sign_in_at = signed_in
        record(db, user, "sign_in", {"method": token.provider})
