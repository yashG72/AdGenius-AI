"""Evaluation-dashboard and organization-dashboard response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models import DocumentStatus, RunStatus
from app.schemas.campaign import CampaignRead


class IterationScore(BaseModel):
    iteration: int
    overall_score: float
    passed: bool
    scores: dict[str, int]
    issue_counts: dict[str, int]


class RevisionInfo(BaseModel):
    iteration: int
    overall_score: float
    issue_count: int
    routed_to: str


class AgentTiming(BaseModel):
    agent: str
    runs: int
    total_ms: float


class EvaluationSummary(BaseModel):
    run_id: uuid.UUID
    status: RunStatus
    threshold: float
    overall_score: float
    passed: bool
    score_change: float  # latest minus first Critic score (revision effect)
    scores: dict[str, int]
    iterations: list[IterationScore]  # score trend across Critic iterations
    issues: list[dict[str, Any]]
    issues_by_severity: dict[str, int]
    issues_by_dimension: dict[str, int]
    strengths: list[str]
    overall_feedback: str
    revision_history: list[RevisionInfo]
    agent_timings: list[AgentTiming]
    total_agent_ms: float


class DashboardTotals(BaseModel):
    brands: int
    campaigns: int
    documents: int
    documents_indexed: int
    runs: int
    runs_completed: int
    runs_active: int
    runs_awaiting_approval: int
    runs_needing_review: int
    runs_failed: int


class DashboardQuality(BaseModel):
    evaluated_runs: int
    average_score: float | None
    approval_rate: float | None  # share of evaluated runs that passed the Critic
    first_pass_rate: float | None  # passed without any revision
    average_revisions: float | None


class AgentActivity(BaseModel):
    agent: str
    steps: int
    average_ms: float
    failures: int


class RecentStep(BaseModel):
    agent: str
    status: str
    summary: str
    started_at: datetime
    campaign_name: str
    run_version: int
    run_id: uuid.UUID


class RecentDocument(BaseModel):
    id: uuid.UUID
    original_filename: str
    brand_id: uuid.UUID
    brand_name: str
    status: DocumentStatus
    created_at: datetime


class Dashboard(BaseModel):
    organization_id: uuid.UUID
    totals: DashboardTotals
    quality: DashboardQuality
    recent_campaigns: list[CampaignRead]
    agent_activity: list[AgentActivity]
    recent_activity: list[RecentStep]
    recent_documents: list[RecentDocument]
