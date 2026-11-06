from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import User
from app.schemas.user import UserList, UserOut, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserList)
def list_users(db: DbSession) -> UserList:
    """Seeded users, for the "acting as" switcher. Buyers first, then suppliers, by company."""
    users = db.scalars(select(User).order_by(User.role, User.company_name)).all()
    return UserList(items=[UserOut.model_validate(u) for u in users])


@router.get("/me", response_model=UserResponse)
def current_user(user: CurrentUser) -> UserResponse:
    """The user identified by the X-User-Id header."""
    return UserResponse(user=UserOut.model_validate(user))
