import uuid

from app.domain.enums import UserRole
from app.schemas.common import ApiModel, ServerTimed


class UserOut(ApiModel):
    id: uuid.UUID
    name: str
    email: str
    company_name: str
    role: UserRole


class UserList(ServerTimed):
    items: list[UserOut]


class UserResponse(ServerTimed):
    user: UserOut
