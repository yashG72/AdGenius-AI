"""Read-only analytics for the evaluation dashboard and the organization dashboard.

Everything here is derived from data the workflow already stored (versioned outputs,
agent trace, run statuses): no extra LLM calls, and history is never recomputed.
"""

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import (
    AgentRun,
    Brand,
    BrandDocument,
    Campaign,
    CampaignOutput,
    CampaignRun,
    DocumentStatus,
    OutputType,
    RunStatus,
)

SEVERITIES = ("critical", "high", "medium", "low")
ACTIVE = (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.AWAITING_APPROVAL)


# ---------- Per-run evaluation summary ----------


async def evaluation_summary(session: AsyncSession, run: CampaignRun) -> dict[str, Any]:
    evaluations = list(
        await session.scalars(
            select(CampaignOutput.content)
            .where(
                CampaignOutput.run_id == run.id,
                CampaignOutput.output_type == OutputType.EVALUATION,
            )
            .order_by(CampaignOutput.version)
        )
    )
    if not evaluations:
        raise NotFoundError("This run has not been evaluated yet.")
    latest = evaluations[-1]

    iterations = []
    for ev in evaluations:
        counts = Counter(i["severity"] for i in ev["issues"])
        iterations.append(
            {
                "iteration": ev["iteration"],
                "overall_score": ev["overall_score"],
                "passed": ev["passed"],
                "scores": ev["scores"],
                "issue_counts": {s: counts.get(s, 0) for s in SEVERITIES},
            }
        )

    final = await session.scalar(
        select(CampaignOutput.content)
        .where(
            CampaignOutput.run_id == run.id,
            CampaignOutput.output_type == OutputType.FINAL_CAMPAIGN,
        )
        .order_by(CampaignOutput.version.desc())
        .limit(1)
    )
    revisions = [
        {
            "iteration": r["iteration"],
            "overall_score": r["overall_score"],
            "issue_count": len(r["issues"]),
            "routed_to": r["routed_to"],
        }
        for r in (final or {}).get("revision_history", [])
    ]

    timing_rows = await session.execute(
        select(AgentRun.agent, func.count(), func.sum(AgentRun.duration_ms))
        .where(AgentRun.run_id == run.id)
        .group_by(AgentRun.agent)
        .order_by(func.min(AgentRun.sequence))
    )
    agent_timings = [
        {"agent": agent, "runs": runs, "total_ms": round(total or 0, 1)}
        for agent, runs, total in timing_rows.all()
    ]

    first = evaluations[0]["overall_score"]
    return {
        "run_id": run.id,
        "status": run.status,
        "threshold": latest["threshold"],
        "overall_score": latest["overall_score"],
        "passed": latest["passed"],
        "score_change": round(latest["overall_score"] - first, 1),
        "scores": latest["scores"],
        "iterations": iterations,
        "issues": latest["issues"],
        "issues_by_severity": iterations[-1]["issue_counts"],
        "issues_by_dimension": dict(Counter(i["dimension"] for i in latest["issues"])),
        "strengths": latest["strengths"],
        "overall_feedback": latest["overall_feedback"],
        "revision_history": revisions,
        "agent_timings": agent_timings,
        "total_agent_ms": round(sum(t["total_ms"] for t in agent_timings), 1),
    }


# ---------- Organization dashboard ----------


async def organization_dashboard(
    session: AsyncSession, organization_id: uuid.UUID, *, activity_days: int = 30
) -> dict[str, Any]:
    active_brand = (Brand.organization_id == organization_id) & Brand.deleted_at.is_(None)

    brands = await session.scalar(select(func.count()).select_from(Brand).where(active_brand))
    campaigns = await session.scalar(
        select(func.count())
        .select_from(Campaign)
        .join(Brand, Brand.id == Campaign.brand_id)
        .where(active_brand)
    )
    doc_counts = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(BrandDocument.status == DocumentStatus.INDEXED),
            )
            .select_from(BrandDocument)
            .join(Brand, Brand.id == BrandDocument.brand_id)
            .where(active_brand, BrandDocument.status != DocumentStatus.DELETED)
        )
    ).one()
    run_status = dict(
        (
            await session.execute(
                select(CampaignRun.status, func.count())
                .where(CampaignRun.organization_id == organization_id)
                .group_by(CampaignRun.status)
            )
        ).all()
    )

    # Quality: runs the Critic finished with (passed or flagged for review).
    evaluated = (
        select(
            CampaignRun.id,
            CampaignRun.status,
            CampaignRun.overall_score,
            func.count(CampaignOutput.id).label("evaluations"),
        )
        .join(
            CampaignOutput,
            (CampaignOutput.run_id == CampaignRun.id)
            & (CampaignOutput.output_type == OutputType.EVALUATION),
        )
        .where(
            CampaignRun.organization_id == organization_id,
            CampaignRun.status.in_([RunStatus.COMPLETED, RunStatus.NEEDS_REVIEW]),
        )
        .group_by(CampaignRun.id)
        .subquery()
    )
    quality = (
        await session.execute(
            select(
                func.count(),
                func.avg(evaluated.c.overall_score),
                func.avg(evaluated.c.evaluations - 1),
                func.sum(case((evaluated.c.status == RunStatus.COMPLETED, 1), else_=0)),
                func.sum(
                    case(
                        (
                            (evaluated.c.status == RunStatus.COMPLETED)
                            & (evaluated.c.evaluations == 1),
                            1,
                        ),
                        else_=0,
                    )
                ),
            )
        )
    ).one()
    evaluated_runs, avg_score, avg_revisions, approved, first_pass = quality

    since = datetime.now(UTC) - timedelta(days=activity_days)
    activity = await session.execute(
        select(
            AgentRun.agent,
            func.count(),
            func.avg(AgentRun.duration_ms),
            func.count().filter(AgentRun.status == "failed"),
        )
        .join(CampaignRun, CampaignRun.id == AgentRun.run_id)
        .where(CampaignRun.organization_id == organization_id, AgentRun.started_at >= since)
        .group_by(AgentRun.agent)
        .order_by(func.count().desc())
    )
    recent_steps = await session.execute(
        select(AgentRun, Campaign.name, CampaignRun.version, CampaignRun.id)
        .join(CampaignRun, CampaignRun.id == AgentRun.run_id)
        .join(Campaign, Campaign.id == CampaignRun.campaign_id)
        .where(CampaignRun.organization_id == organization_id)
        .order_by(AgentRun.started_at.desc())
        .limit(10)
    )
    recent_documents = await session.execute(
        select(BrandDocument, Brand.name)
        .join(Brand, Brand.id == BrandDocument.brand_id)
        .where(active_brand, BrandDocument.status != DocumentStatus.DELETED)
        .order_by(BrandDocument.created_at.desc())
        .limit(5)
    )

    def rate(part, whole):
        return round(part / whole, 3) if whole else None

    return {
        "organization_id": organization_id,
        "totals": {
            "brands": brands or 0,
            "campaigns": campaigns or 0,
            "documents": doc_counts[0],
            "documents_indexed": doc_counts[1],
            "runs": sum(run_status.values()),
            "runs_completed": run_status.get(RunStatus.COMPLETED, 0),
            "runs_active": sum(run_status.get(s, 0) for s in ACTIVE),
            "runs_awaiting_approval": run_status.get(RunStatus.AWAITING_APPROVAL, 0),
            "runs_needing_review": run_status.get(RunStatus.NEEDS_REVIEW, 0),
            "runs_failed": run_status.get(RunStatus.FAILED, 0),
        },
        "quality": {
            "evaluated_runs": evaluated_runs or 0,
            "average_score": round(float(avg_score), 1) if avg_score is not None else None,
            "approval_rate": rate(approved or 0, evaluated_runs),
            "first_pass_rate": rate(first_pass or 0, evaluated_runs),
            "average_revisions": (
                round(float(avg_revisions), 2) if avg_revisions is not None else None
            ),
        },
        "agent_activity": [
            {
                "agent": agent,
                "steps": steps,
                "average_ms": round(float(avg_ms or 0), 1),
                "failures": failures,
            }
            for agent, steps, avg_ms, failures in activity.all()
        ],
        "recent_activity": [
            {
                "agent": step.agent,
                "status": step.status,
                "summary": step.summary,
                "started_at": step.started_at,
                "campaign_name": name,
                "run_version": version,
                "run_id": run_id,
            }
            for step, name, version, run_id in recent_steps.all()
        ],
        "recent_documents": [
            {
                "id": doc.id,
                "original_filename": doc.original_filename,
                "brand_id": doc.brand_id,
                "brand_name": brand_name,
                "status": doc.status,
                "created_at": doc.created_at,
            }
            for doc, brand_name in recent_documents.all()
        ],
    }
