from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

hasher = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
dummy_hash = hasher.hash("constant-non-user-timing-comparison")
attempts = defaultdict(deque)
lock = Lock()


def limit_auth(request: Request):
    """Development per-process limiter; proxy must add shared limits in production."""
    key = request.client.host if request.client else "local"
    with lock:
        current = monotonic()
        queue = attempts[key]
        while queue and current - queue[0] > 60:
            queue.popleft()
        if len(queue) >= 15:
            raise HTTPException(429, "Too many sign-in attempts. Try again in a minute.")
        queue.append(current)
        if len(attempts) > 10000:
            for old in list(attempts):
                if not attempts[old] or current - attempts[old][-1] > 60:
                    del attempts[old]


def token(user: User):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user.id, "ver": user.token_version, "iat": now, "exp": now + timedelta(minutes=settings().access_token_minutes), "iss": "packwise"}, settings().secret_key, algorithm="HS256")


def current_user(auth: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    try:
        if auth is None:
            raise ValueError("No token")
        payload = jwt.decode(auth.credentials, settings().secret_key, algorithms=["HS256"], issuer="packwise", options={"require": ["exp", "sub", "iat", "iss", "ver"]})
        user = db.get(User, payload["sub"])
        if user is None or user.token_version != payload["ver"]:
            raise ValueError("Invalid session")
        return user
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, "Please sign in again.", headers={"WWW-Authenticate": "Bearer"}) from None


def reviewer(user: User = Depends(current_user)):
    if not user.is_reviewer:
        raise HTTPException(403, "A verified packaging reviewer is required.")
    return user
