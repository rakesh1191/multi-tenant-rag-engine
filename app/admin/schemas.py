import uuid
from pydantic import BaseModel
from app.auth.schemas import UserOut


class TenantStats(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    document_count: int
    chunk_count: int
    total_storage_bytes: int
    user_count: int
    query_count: int


class AdminUsersResponse(BaseModel):
    items: list[UserOut]
    total: int
