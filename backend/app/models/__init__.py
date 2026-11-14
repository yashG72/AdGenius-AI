"""ORM models.

Every model must be imported here: Alembic inspects `Base.metadata` to autogenerate
migrations, and a model that is never imported is invisible to it.
"""

from app.db.base import Base
from app.models.brand import Brand
from app.models.campaign import (
    AgentRun,
    Approval,
    ApprovalStatus,
    Campaign,
    CampaignOutput,
    CampaignRun,
    OutputType,
    RunStatus,
)
from app.models.document import BrandDocument, DocumentFormat, DocumentStatus, DocumentType
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.user import User

__all__ = [
    "AgentRun",
    "Approval",
    "ApprovalStatus",
    "Base",
    "Brand",
    "Campaign",
    "CampaignOutput",
    "CampaignRun",
    "OutputType",
    "RunStatus",
    "BrandDocument",
    "DocumentFormat",
    "DocumentStatus",
    "DocumentType",
    "Membership",
    "MembershipRole",
    "Organization",
    "RefreshToken",
    "User",
]
