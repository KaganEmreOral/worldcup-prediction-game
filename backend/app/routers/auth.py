import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, get_user_by_username, hash_password, verify_password
from app.database import get_db
from app.models import User
from app.schemas import AuthResponse, TokenResponse, UserLogin, UserRegister, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def _normalize_username(raw: str) -> str:
    return raw.strip().lower()


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    username = _normalize_username(data.username)
    logger.info("auth.register attempt username=%s", username)

    if not _USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="Username may only contain letters, numbers, and underscores")

    existing = await get_user_by_username(db, username)
    if existing:
        logger.warning("auth.register rejected username=%s reason=already_taken", username)
        raise HTTPException(status_code=400, detail="Username already taken")

    try:
        user = User(
            username=username,
            name=data.username.strip(),
            password_hash=hash_password(data.password),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        token = create_access_token(user.id, user.is_admin)
        logger.info("auth.register success user_id=%s username=%s", user.id, username)
        return AuthResponse(access_token=token, user=user)
    except IntegrityError as exc:
        logger.warning("auth.register integrity error username=%s err=%s", username, exc.orig)
        raise HTTPException(status_code=400, detail="Username already taken") from exc
    except Exception:
        logger.exception("auth.register unexpected error username=%s", username)
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    username = _normalize_username(data.username)
    logger.info("auth.login attempt username=%s", username)

    user = await get_user_by_username(db, username)
    if not user or not verify_password(data.password, user.password_hash):
        logger.warning("auth.login failed username=%s reason=invalid_credentials", username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(user.id, user.is_admin)
    logger.info("auth.login success user_id=%s username=%s admin=%s", user.id, username, user.is_admin)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user
