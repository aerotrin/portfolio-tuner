from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import PyJWK

from backend.shared.config import config

_security = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> None:
    """Validate a Supabase-issued JWT (ES256 / P-256). Raises 401 if invalid or expired."""
    token = credentials.credentials
    try:
        public_key = PyJWK.from_json(config.supabase_jwt_public_key)
        jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    """Decode a Supabase JWT and return the user UUID (sub claim). Raises 401 if invalid."""
    token = credentials.credentials
    try:
        public_key = PyJWK.from_json(config.supabase_jwt_public_key)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated",
        )
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
