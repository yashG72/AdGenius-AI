"""Persist workflow progress to PostgreSQL as it happens.

Called after every agent node finishes. It appends the node's trace events to
`agent_runs` and stores its output as a NEW versioned row in `campaign_outputs`
(script v1, script v2 after a revision, ... nothing is overwritten). Each step is
committed immediately so the API and the live event stream see progress mid-run.

Uses its OWN database session: the Brand Research agent queries the database while the
Competitor agent runs in parallel, and one AsyncSession must never be used concurrently.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, CampaignOutput, CampaignRun, OutputType

# node name -> how to extract its output from the node's state update
NODE_OUTPUTS: dict[str, tuple[OutputType, Any]] = {
    "campaign_manager": (OutputType.EXECUTION_PLAN, lambda u: u.get("plan")),
    "brand_research": (
        OutputType.BRAND_RESEARCH,
        lambda u: (
            u.get("brand_research")
            and {"research": u["brand_research"], "sources": u.get("brand_sources", [])}
        ),
    ),
    "competitor_research": (OutputType.COMPETITOR_RESEARCH, lambda u: u.get("competitor_research")),
    "creative_strategist": (OutputType.CONCEPTS, lambda u: u.get("concepts")),
    "scriptwriter": (OutputType.SCRIPT, lambda u: u.get("script")),
    "visual_director": (OutputType.STORYBOARD, lambda u: u.get("storyboard")),
    "critic": (OutputType.EVALUATION, lambda u: u.get("evaluation")),
    "finalize": (OutputType.FINAL_CAMPAIGN, lambda u: u.get("final")),
}


class RunRecorder:
    def __init__(self, session: AsyncSession, run_id: uuid.UUID) -> None:
        self.session = session
        self.run_id = run_id

    async def _next(self, column, *filters) -> int:
        current = await self.session.scalar(select(func.max(column)).where(*filters))
        return (current or 0) + 1

    async def on_update(self, node: str, update: dict[str, Any]) -> None:
        sequence = await self._next(AgentRun.sequence, AgentRun.run_id == self.run_id)
        for event in update.get("events") or []:
            self.session.add(
                AgentRun(
                    run_id=self.run_id,
                    sequence=sequence,
                    agent=event.get("agent", node),
                    status=event.get("status", "completed"),
                    summary=event.get("summary", ""),
                    started_at=datetime.fromisoformat(event["started_at"]),
                    duration_ms=event.get("duration_ms", 0.0),
                )
            )
            sequence += 1

        if node in NODE_OUTPUTS:
            output_type, extract = NODE_OUTPUTS[node]
            content = extract(update)
            if content:
                version = await self._next(
                    CampaignOutput.version,
                    CampaignOutput.run_id == self.run_id,
                    CampaignOutput.output_type == output_type,
                )
                self.session.add(
                    CampaignOutput(
                        run_id=self.run_id,
                        output_type=output_type,
                        version=version,
                        content=content,
                    )
                )
                if output_type is OutputType.EVALUATION:
                    run = await self.session.get(CampaignRun, self.run_id)
                    run.overall_score = content.get("overall_score")
        await self.session.commit()
