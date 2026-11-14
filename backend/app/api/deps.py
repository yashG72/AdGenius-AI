"""Reusable FastAPI dependencies.

Later phases add the DB session, the current user and organization-membership checks here.
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]
