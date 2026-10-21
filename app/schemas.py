from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import TicketPriority, TicketStatus, UserRole


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=3, max_length=255)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.user


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_superuser: bool
    role: UserRole
    created_at: datetime


class UserList(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[UserRead]


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    jti: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    user_agent: str | None = None
    client_ip: str | None = None
    active: bool = True


class TokenPayload(BaseModel):
    sub: str | None = None


class CommentBase(BaseModel):
    author: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1)


class CommentCreate(CommentBase):
    pass


class CommentRead(CommentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    created_at: datetime


class TicketBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: TicketStatus = TicketStatus.open
    priority: TicketPriority = TicketPriority.medium


class TicketCreate(TicketBase):
    pass


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: TicketStatus | None = None
    priority: TicketPriority | None = None


class TicketRead(TicketBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int | None = None
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketRead):
    comments: list[CommentRead] = []


class TicketList(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[TicketRead]