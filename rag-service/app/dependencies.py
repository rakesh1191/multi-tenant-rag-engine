"""Top-level FastAPI dependencies re-exported for convenience."""
from app.auth.dependencies import (  # noqa: F401
    get_current_tenant,
    get_current_user,
    require_admin,
)
from app.common.database import get_db  # noqa: F401
