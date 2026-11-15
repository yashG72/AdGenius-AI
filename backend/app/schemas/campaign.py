"""Campaign, run, approval and output API schemas."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.agents.schemas import BriefFields
from app.models import ApprovalStatus, OutputType, RunStatus

CampaignName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]


class CampaignCreate(BaseModel):
    brand_id: uuid.UUID
    name: CampaignName
    brief: BriefFields


class CampaignUpdate(BaseModel):
    """Changes apply to FUTURE runs only - earlier runs keep their brief snapshot."""

    name: CampaignName | None = None
    brief: BriefFields | None = None


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    version: int
    status: RunStatus
    overall_score: float | None
    error_message: str | None
    parent_run_id: uuid.UUID | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    brand_id: uuid.UUID
    created_by_id: uuid.UUID | None
    name: str
    brief: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    latest_run: RunSummary | None = None
    run_count: int = 0


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence: int
    agent: str
    status: str
    summary: str
    started_at: datetime
    duration_ms: float


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    kind: str
    round: int
    status: ApprovalStatus
    payload: dict[str, Any]
    decision: dict[str, Any] | None
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime


class OutputVersionInfo(BaseModel):
    output_type: OutputType
    latest_version: int
    versions: int


class RunDetail(RunSummary):
    brief_snapshot: dict[str, Any]
    agent_runs: list[AgentRunRead]
    pending_approval: ApprovalRead | None
    outputs: list[OutputVersionInfo]


class OutputRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: uuid.UUID
    output_type: OutputType
    version: int
    versions: int = Field(description="How many versions of this output the run produced.")
    content: dict[str, Any]
    source: str = Field(description='"agent" (workflow) or "human" (saved from an editor).')
    created_by_id: uuid.UUID | None
    created_at: datetime


class ApproveRequest(BaseModel):
    concept_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)
    ]
    feedback: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = (
        None
    )


class RejectRequest(BaseModel):
    feedback: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
