"""极简 JWT 鉴权（开发模式：未带 token → 返回默认用户）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt

from ..core.config import settings

# 开发用默认用户 ID
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def create_access_token(user_id: str | uuid.UUID, hours: int | None = None) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc)
        + timedelta(hours=hours or settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


class CurrentUser:
    def __init__(self, id: str):
        self.id = id


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    """开发模式：没 token 就返回默认用户。生产环境应改为强制要求。"""
    if not authorization:
        return CurrentUser(id=str(DEFAULT_USER_ID))

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid auth header")

    token = parts[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        uid = payload.get("sub")
        if not uid:
            raise HTTPException(status_code=401, detail="Invalid token")
        return CurrentUser(id=uid)
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Token invalid: {e}")