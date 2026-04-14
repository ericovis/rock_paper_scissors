import os

from fastapi import Cookie, HTTPException, status

COOKIE_NAME = "rps_user_id"
COOKIE_MAX_AGE = 315360000  # 10 years
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"


def set_user_cookie(response, user_id: int) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=str(user_id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )


def current_user_id(rps_user_id: str | None = Cookie(default=None)) -> int:
    if not rps_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing rps_user_id cookie",
        )
    try:
        return int(rps_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid rps_user_id cookie",
        )
