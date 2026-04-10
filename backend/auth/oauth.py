"""Google OAuth 2.0 integration.

Flow (redirect-based):
1. Frontend redirects to Google consent screen.
2. Google redirects back with an authorization code.
3. Backend exchanges code → id_token → extracts email + sub.
4. Backend creates / retrieves user, returns JWT pair.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel

from backend.config import get_settings

settings = get_settings()

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleUserInfo(BaseModel):
    """Relevant fields from Google's userinfo endpoint."""
    sub: str           # Google's unique user ID
    email: str
    email_verified: bool = False
    name: str | None = None
    picture: str | None = None


class OAuthError(Exception):
    """Raised when OAuth exchange fails."""


async def exchange_google_code(
    code: str,
    redirect_uri: str,
) -> GoogleUserInfo:
    """Exchange a Google authorization code for user info.

    Args:
        code: Authorization code from Google redirect.
        redirect_uri: Must match the URI registered in Google console.

    Returns:
        GoogleUserInfo with email and sub.

    Raises:
        OAuthError: if the exchange or userinfo request fails.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        # 1. Exchange code for tokens
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

        if token_resp.status_code != 200:
            raise OAuthError(
                f"Google token exchange failed: {token_resp.status_code} — "
                f"{token_resp.text}"
            )

        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            raise OAuthError("No access_token in Google response")

        # 2. Fetch user info
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if userinfo_resp.status_code != 200:
            raise OAuthError(
                f"Google userinfo failed: {userinfo_resp.status_code}"
            )

        data = userinfo_resp.json()

    return GoogleUserInfo(
        sub=data["sub"],
        email=data["email"],
        email_verified=data.get("email_verified", False),
        name=data.get("name"),
        picture=data.get("picture"),
    )
