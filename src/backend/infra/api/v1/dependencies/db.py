from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.infra.api.v1.dependencies.auth import get_current_user_id


def get_user_db(
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> Session:
    """
    Yield a DB session scoped to the authenticated user.

    Switches the PostgreSQL role to 'authenticated' and sets the JWT sub claim
    so that RLS policies enforced via auth.uid() apply correctly.
    """
    db = request.app.state.SessionLocal()
    try:
        db.execute(text("SET LOCAL ROLE authenticated"))
        db.execute(
            text("SELECT set_config('request.jwt.claim.sub', :uid, true)"),
            {"uid": user_id},
        )
        yield db
    finally:
        db.close()


def get_admin_db(request: Request) -> Session:
    """
    Yield a DB session as the postgres superuser.

    RLS is bypassed by default for superusers. Use only for admin operations
    that are already protected by the backend's authentication middleware.
    """
    db = request.app.state.SessionLocal()
    try:
        yield db
    finally:
        db.close()
