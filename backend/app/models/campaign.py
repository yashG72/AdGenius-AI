"""Campaigns, versioned runs, agent trace, outputs and human approvals.

    campaign 1--* campaign_run (version 1, 2, 3 ... never overwritten)
    campaign_run 1--* agent_run        (execution trace, one row per agent step)
    campaign_run 1--* campaign_output  (every version of every output is kept)
    campaign_run 1--* approval         (human-in-the-loop decisions)

A run's id doubles as its LangGraph thread_id, linking these rows to the workflow's
checkpoints. Runs snapshot the brief and brand profile at start, so editing the
campaign later never changes what an earlier run was based on.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _pg_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda members: [m.value for m in members])


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"  # passed the Critic
    NEEDS_REVIEW = "needs_review"  # below threshold after max revisions
    CONCEPTS_REJECTED = "concepts_rejected"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_STATUSES


TERMINAL_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.NEEDS_REVIEW,
    RunStatus.CONCEPTS_REJECTED,
    RunStatus.FAILED,
}


class OutputType(enum.StrEnum):
    EXECUTION_PLAN = "execution_plan"
    BRAND_RESEARCH = "brand_research"
    COMPETITOR_RESEARCH = "competitor_research"
    CONCEPTS = "concepts"
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    EVALUATION = "evaluation"
    FINAL_CAMPAIGN = "final_campaign"


class ApprovalStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Campaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(300))
    brief: Mapped[dict[str, Any]] = mapped_column(JSONB)  # validated BriefFields


class CampaignRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaign_runs"
    __table_args__ = (UniqueConstraint("campaign_id", "version"),)

    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaign_runs.id", ondelete="SET NULL")
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[RunStatus] = mapped_column(
        _pg_enum(RunStatus, "run_status"), default=RunStatus.QUEUED, index=True
    )
    brief_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    brand_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    overall_score: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRun(UUIDPrimaryKeyMixin, Base):
    """One step of the execution trace (persisted live while the workflow runs)."""

    __tablename__ = "agent_runs"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaign_runs.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    agent: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float] = mapped_column(Float, default=0)


class CampaignOutput(UUIDPrimaryKeyMixin, Base):
    """Every version of every output. Revisions add rows; nothing is overwritten."""

    __tablename__ = "campaign_outputs"
    __table_args__ = (UniqueConstraint("run_id", "output_type", "version"),)

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaign_runs.id", ondelete="CASCADE"))
    output_type: Mapped[OutputType] = mapped_column(_pg_enum(OutputType, "output_type"))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # "agent" = produced by the workflow; "human" = saved from the script/storyboard editor.
    source: Mapped[str] = mapped_column(String(20), default="agent", server_default="agent")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class Approval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        # At most one open approval per run.
        Index(
            "uq_approvals_run_id_pending",
            "run_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaign_runs.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(50), default="concept_selection")
    round: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[ApprovalStatus] = mapped_column(
        _pg_enum(ApprovalStatus, "approval_status"), default=ApprovalStatus.PENDING
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)  # what the human is shown
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the worker has fed the decision into the workflow (idempotency marker).
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
