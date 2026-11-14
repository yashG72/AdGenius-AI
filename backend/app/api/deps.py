"""Reusable FastAPI dependencies.

Endpoints declare what they need (`session: DbSessionDep`) and FastAPI provides it.
Tests swap these out via `app.dependency_overrides`.
Later phases add the current user and organization-membership checks here.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
