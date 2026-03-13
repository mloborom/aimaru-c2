from typing import Optional
from datetime import datetime
from pydantic import BaseModel

# api/app/schemas.py (append these)
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class MCPKey(BaseModel):
    id: str
    key_id: str
    label: Optional[str] = None
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked: bool = False

class MCPKeyCreate(BaseModel):
    label: Optional[str] = None
    ttl_minutes: Optional[int] = None

class MCPKeyCreateResp(BaseModel):
    token: str         

class LoginReq(BaseModel):
    username: str
    password: str

class LoginResp(BaseModel):
    access_token: str
    user: dict | None = None

class UserOut(BaseModel):
    id: str
    username: str
    role: str
    disabled: bool

class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class UserPatch(BaseModel):
    role: str | None = None
    disabled: bool | None = None