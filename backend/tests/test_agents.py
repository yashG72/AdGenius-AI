"""Multi-agent workflow: routing, human approval, revision loop, failures, durability."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.checkpointer import postgres_checkpointer
from app.agents.deps import AgentDeps
from app.agents.nodes.approval import ConceptDecision
from app.agents.runner import CampaignWorkflow
from app.agents.schemas import (
    BrandResearch,
    CampaignBrief,
    Concept,
    ConceptSet,
    CriticReview,
    DimensionScores,
    ExecutionPlan,
    ImagePrompt,
    Issue,
    Script,
    ScriptScene,
    Storyboard,
    StoryboardScene,
)
from app.agents.timing import normalize_timeline
from app.core.config import get_settings
from app.core.exceptions import BadRequestError, ConflictError
from app.llm.client import LLMError
from app.rag.types import RetrievedChunk, SearchResult
from app.research.competitor import CompetitorReport
from tests.fakes import FakeLLM

pytestmark = pytest.mark.anyio

ORG_ID, BRAND_ID = uuid.uuid4(), uuid.uuid4()
BRAND = {
    "id": str(BRAND_ID),
    "organization_id": str(ORG_ID),
    "name": "MANO",
    "industry": "Beverages",
    "brand_voice": "Witty",
    "content_restrictions": ["Never say 'healthy' or 'boosts immunity'"],
    "brand_colors": [{"name": "Mango", "hex": "#FFB300"}],
    "competitors": [{"name": "FizzCo"}],
}
BRIEF = CampaignBrief(
    brand_id=BRAND_ID,
    campaign_name="Campus Launch",
    objective="Brand awareness",
    target_audience="College students 18-25",
    platform="instagram",
    duration_seconds=30,
    video_format="9:16",
    num_concepts=3,
    tone="Youthful and humorous",
)


# ---------- scripted model outputs ----------


def seq(*items):
    """Callable for FakeLLM that returns the next item on each call (last one repeats)."""
    state = {"i": 0}

    def next_item(system, user):
        item = items[min(state["i"], len(items) - 1)]
        state["i"] += 1
        if isinstance(item, Exception):
            raise item
        return item(system, user) if callable(item) else item

    return next_item


PLAN = ExecutionPlan(
    campaign_summary="30s Reel",
    brand_research_questions=["Voice?", "Rules?"],
    competitor_research_focus="campus drinks ads",
)
RESEARCH = BrandResearch(
    summary="Witty brand",
    tone_of_voice="Witty",
    prohibited_claims=["Do not say 'healthy'"],
    cited_sources=[1, 99],
)


def concepts(prefix="Idea") -> ConceptSet:
    items = [
        Concept(
            concept_id=f"x{i}",
            title=f"{prefix} {i}",
            core_idea="c",
            creative_angle="a",
            target_emotion="joy",
            opening_hook="h",
            storytelling_approach="s",
            key_message="k",
            unique_selling_proposition="u",
            call_to_action="cta",
            reasoning="r",
        )
        for i in (1, 2, 3)
    ]
    return ConceptSet(
        concepts=items,
        recommended_concept_id="x2",
        recommendation_reasoning="best",
        campaign_messaging="Fizz without the fall",
    )


def script(voiceover="Fizz without the fall") -> Script:
    return Script(
        title="Crash-free",
        opening_hook="Exam week...",
        call_to_action="Grab a MANO",
        scenes=[
            ScriptScene(scene_number=9, duration_seconds=d, visual_summary="v", voiceover=voiceover)
            for d in (10, 10, 13)
        ],
    )


def storyboard() -> Storyboard:
    prompt = ImagePrompt(
        prompt="p",
        visual_style="warm",
        subject="s",
        environment="e",
        lighting="l",
        composition="c",
        camera_perspective="low",
        aspect_ratio="16:9",
        negative_prompt="text",
    )
    return Storyboard(
        visual_style="warm",
        consistency_notes="same student",
        scenes=[
            StoryboardScene(
                scene_number=1,
                duration_seconds=d,
                scene_description="d",
                visual_direction="v",
                camera_angle="eye",
                camera_movement="pan",
                lighting="day",
                transition="cut",
                image_prompt=prompt,
            )
            for d in (15, 14)
        ],
    )


def review(score: int, target: str = "storyboard", critical: bool = False) -> CriticReview:
    issues = (
        []
        if score >= 80 and not critical
        else [
            Issue(
                dimension="visual_consistency",
                severity="critical" if critical else "medium",
                target=target,
                description="problem",
                suggestion="fix it",
            )
        ]
    )
    return CriticReview(
        scores=DimensionScores(**dict.fromkeys(DimensionScores.model_fields, score)),
        issues=issues,
        strengths=["hook"],
        overall_feedback="feedback",
    )


def llm(critic=None, strategist=None, **overrides) -> FakeLLM:
    return FakeLLM(
        {
            ExecutionPlan: overrides.get("plan", PLAN),
            BrandResearch: overrides.get("research", RESEARCH),
            ConceptSet: strategist or seq(concepts()),
            Script: overrides.get("script", seq(lambda s, u: script())),
            Storyboard: seq(lambda s, u: storyboard()),
            CriticReview: critic or seq(review(90)),
        }
    )


class FakeKnowledge:
    def __init__(self):
        self.queries = []

    async def search(self, scope, query, *, top_k=None, rewrite=True, rerank=True, mode="hybrid"):
        self.queries.append((scope, query, rewrite))
        chunk = RetrievedChunk(
            point_id=f"p-{len(self.queries) % 2}",
            document_id=uuid.uuid4(),
            original_filename="guidelines.pdf",
            document_type="brand_guidelines",
            source_page=2,
            chunk_index=0,
            text=f"Rule text {len(self.queries) % 2}",
            fusion_score=1.0,
        )
        return SearchResult(queries=[query], chunks=[chunk])


class FakeCompetitor:
    def __init__(self, fail: bool = False):
        self.fail, self.contexts = fail, []

    async def research(self, ctx, *, max_queries=None):
        self.contexts.append(ctx)
        if self.fail:
            raise RuntimeError("tavily down")
        return CompetitorReport(
            brand_name="MANO",
            summary="FizzCo dominates",
            competitors=[],
            market_trends=[],
            opportunities=[],
            sources=[],
            queries=["q"],
            failed_queries=[],
            unsupported_claims_removed=0,
            search_calls=1,
            generated_at=datetime.now(UTC),
        )


def workflow(fake_llm, *, knowledge=None, competitor=None, checkpointer=None, **settings):
    s = get_settings().model_copy(update={"agent_retry_initial_seconds": 0, **settings})
    deps = AgentDeps(
        llm=fake_llm, settings=s, knowledge=knowledge, competitor_researcher=competitor
    )
    return CampaignWorkflow(deps, checkpointer or InMemorySaver())


def agents_run(view) -> list[str]:
    return [e["agent"] for e in view.values["events"]]


def calls(fake: FakeLLM, schema: str) -> int:
    return sum(1 for name, *_ in fake.calls if name == schema)


# ---------- Happy path ----------


async def test_full_run_pauses_for_approval_then_completes() -> None:
    fake, knowledge, competitor = llm(), FakeKnowledge(), FakeCompetitor()
    wf = workflow(fake, knowledge=knowledge, competitor=competitor)

    paused = await wf.start("run-1", BRIEF, BRAND)

    assert paused.status == "awaiting_concept_approval"
    assert [c["concept_id"] for c in paused.pending_approval["concepts"]] == ["C1", "C2", "C3"]
    assert paused.pending_approval["recommended_concept_id"] == "C2"  # x2 remapped
    assert set(agents_run(paused)) >= {
        "campaign_manager",
        "brand_research",
        "competitor_research",
        "merge_research",
        "creative_strategist",
    }
    assert calls(fake, "Script") == 0  # nothing produced before human approval
    # Brand research used RAG, scoped to this org + brand, without query rewriting.
    assert [q for _, q, _ in knowledge.queries] == ["Voice?", "Rules?"]
    assert all(
        s.organization_id == ORG_ID and s.brand_id == BRAND_ID and not rw
        for s, _, rw in knowledge.queries
    )
    assert paused.values["brand_research"]["cited_sources"] == [1]  # 99 was invented
    assert "FizzCo dominates" in paused.values["research_digest"]  # parallel branch merged
    assert "PROHIBITED" in paused.values["research_digest"]

    done = await wf.resume("run-1", ConceptDecision(action="approve", concept_id="C2"))

    assert done.status == "approved"
    final = done.values["final"]
    assert final["creative_strategy"]["selected_concept_id"] == "C2"
    scenes = final["script"]["scenes"]
    assert [s["scene_number"] for s in scenes] == [1, 2, 3]
    assert scenes[-1]["end_time"] == 30 and final["script"]["timing_adjusted"]  # 33s -> 30s
    assert final["storyboard"]["scenes"][-1]["end_time"] == 30
    assert {p["aspect_ratio"] for p in final["image_prompts"]} == {"9:16"}  # brief wins
    assert final["evaluation"]["overall_score"] == 90 and final["evaluation"]["passed"]
    assert final["revision_history"] == []
    assert agents_run(done)[-4:] == ["scriptwriter", "visual_director", "critic", "finalize"]


async def test_events_record_timing_and_summaries() -> None:
    wf = workflow(llm(), knowledge=FakeKnowledge(), competitor=FakeCompetitor())

    view = await wf.start("run-ev", BRIEF, BRAND)

    for event in view.values["events"]:
        assert event["status"] in ("completed", "skipped", "failed")
        assert event["duration_ms"] >= 0 and event["started_at"]
    manager = next(e for e in view.values["events"] if e["agent"] == "campaign_manager")
    assert "2 research questions" in manager["summary"]


# ---------- Research branches ----------


async def test_competitor_research_skipped_when_disabled_or_unconfigured() -> None:
    no_web = workflow(llm(), competitor=None)
    view = await no_web.start("run-a", BRIEF, BRAND)
    event = next(e for e in view.values["events"] if e["agent"] == "competitor_research")
    assert event["status"] == "skipped" and "not configured" in event["summary"]

    competitor = FakeCompetitor()
    disabled = workflow(llm(), competitor=competitor)
    brief = BRIEF.model_copy(update={"competitor_research": False})
    view = await disabled.start("run-b", brief, BRAND)
    assert competitor.contexts == []
    assert view.status == "awaiting_concept_approval"


async def test_competitor_failure_degrades_instead_of_failing() -> None:
    wf = workflow(llm(), competitor=FakeCompetitor(fail=True))

    view = await wf.start("run-c", BRIEF, BRAND)

    event = next(e for e in view.values["events"] if e["agent"] == "competitor_research")
    assert event["status"] == "failed"
    assert view.status == "awaiting_concept_approval"  # run carried on


async def test_no_documents_is_recorded_as_knowledge_gap() -> None:
    view = await workflow(llm(), knowledge=None).start("run-d", BRIEF, BRAND)

    gaps = view.values["brand_research"]["knowledge_gaps"]
    assert any("No brand documents" in g for g in gaps)


# ---------- Human approval ----------


async def test_rejecting_concepts_regenerates_with_feedback() -> None:
    fake = llm(strategist=seq(concepts("Old"), concepts("New")))
    wf = workflow(fake)
    await wf.start("run-r", BRIEF, BRAND)

    view = await wf.resume("run-r", ConceptDecision(action="reject", feedback="Make it funnier"))

    assert view.status == "awaiting_concept_approval"
    assert view.pending_approval["round"] == 2
    assert view.pending_approval["concepts"][0]["title"] == "New 1"
    last_strategist_prompt = [u for n, _, u in fake.calls if n == "ConceptSet"][-1]
    assert "Make it funnier" in last_strategist_prompt and "Old 1" in last_strategist_prompt


async def test_concept_round_limit_ends_run() -> None:
    wf = workflow(llm(), agent_max_concept_rounds=1)
    await wf.start("run-lim", BRIEF, BRAND)

    view = await wf.resume("run-lim", ConceptDecision(action="reject", feedback="No"))

    assert view.status == "concepts_rejected"
    assert view.values["final"]["script"] is None


async def test_invalid_decisions_are_refused() -> None:
    wf = workflow(llm())
    with pytest.raises(ConflictError):
        await wf.resume("never-started", ConceptDecision(action="approve", concept_id="C1"))
    await wf.start("run-x", BRIEF, BRAND)
    with pytest.raises(ConflictError):
        await wf.start("run-x", BRIEF, BRAND)  # idempotency: no double start
    with pytest.raises(BadRequestError):
        await wf.resume("run-x", ConceptDecision(action="approve", concept_id="C9"))
    with pytest.raises(ValueError):
        ConceptDecision(action="reject")  # feedback required


# ---------- Critic loop ----------


async def test_storyboard_issues_route_to_visual_director_only() -> None:
    fake = llm(critic=seq(review(60, target="storyboard"), review(88)))
    wf = workflow(fake)
    await wf.start("run-v", BRIEF, BRAND)

    done = await wf.resume("run-v", ConceptDecision(action="approve", concept_id="C1"))

    assert done.status == "approved"
    assert calls(fake, "Script") == 1 and calls(fake, "Storyboard") == 2
    history = done.values["final"]["revision_history"]
    assert [(h["iteration"], h["overall_score"], h["routed_to"]) for h in history] == [
        (1, 60.0, "visual_director")
    ]
    revision_prompt = [u for n, _, u in fake.calls if n == "Storyboard"][-1]
    assert "Fix these issues" in revision_prompt and "fix it" in revision_prompt


async def test_script_issues_regenerate_script_and_storyboard() -> None:
    fake = llm(critic=seq(review(70, target="script"), review(85)))
    done = await _approve(workflow(fake), "run-s")

    assert done.status == "approved"
    assert calls(fake, "Script") == 2 and calls(fake, "Storyboard") == 2


async def test_still_failing_after_max_revisions_needs_human_review() -> None:
    fake = llm(critic=seq(review(55)))
    done = await _approve(workflow(fake), "run-m")

    assert done.status == "needs_human_review"  # never silently approved
    assert calls(fake, "CriticReview") == 3  # initial + 2 revisions
    assert len(done.values["final"]["revision_history"]) == 2
    assert done.values["final"]["script"] is not None  # result preserved


async def test_prohibited_phrase_fails_even_with_high_scores() -> None:
    fake = llm(critic=seq(review(95)), script=seq(lambda s, u: script("MANO is healthy and fun")))
    done = await _approve(workflow(fake, agent_max_revisions=0), "run-p")

    evaluation = done.values["final"]["evaluation"]
    assert evaluation["overall_score"] == 95 and not evaluation["passed"]
    assert any(
        i["severity"] == "critical" and "healthy" in i["description"] for i in evaluation["issues"]
    )
    assert done.status == "needs_human_review"


async def test_transient_llm_errors_are_retried() -> None:
    fake = llm(strategist=seq(LLMError(), concepts()))

    view = await workflow(fake).start("run-retry", BRIEF, BRAND)

    assert view.status == "awaiting_concept_approval"
    assert calls(fake, "ConceptSet") == 2


async def _approve(wf: CampaignWorkflow, thread: str):
    await wf.start(thread, BRIEF, BRAND)
    return await wf.resume(thread, ConceptDecision(action="approve", concept_id="C1"))


# ---------- Durability: real PostgreSQL checkpoints ----------


async def test_postgres_checkpoint_survives_restart(test_database_url: str) -> None:
    thread = f"pg-{uuid.uuid4()}"
    async with postgres_checkpointer(test_database_url) as saver:
        paused = await workflow(llm(), checkpointer=saver).start(thread, BRIEF, BRAND)
        assert paused.status == "awaiting_concept_approval"

    # A brand-new connection and workflow object = a restarted worker.
    async with postgres_checkpointer(test_database_url) as saver:
        wf = workflow(llm(), checkpointer=saver)
        assert (await wf.view(thread)).status == "awaiting_concept_approval"
        done = await wf.resume(thread, ConceptDecision(action="approve", concept_id="C3"))
        assert done.status == "approved"
        assert done.values["final"]["creative_strategy"]["selected_concept_id"] == "C3"
        await saver.adelete_thread(thread)


# ---------- Compliance guardrail phrase extraction ----------


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("Never say 'healthy' or 'boosts immunity'", ["boosts immunity", "healthy"]),
        (
            "Do not use comparative claims (such as 'less sugar than colas')",
            ["less sugar than colas"],
        ),
        ('Avoid the words "detox" and "cure"', ["cure", "detox"]),
        # Regression (live run 2026-11-15): the tagline is REQUIRED, not banned.
        (
            "Do not modify, translate, or abbreviate the official tagline 'Fizz Without the Fall'",
            [],
        ),
        ("Logo must keep clear space around the 'M'", []),
    ],
)
def test_banned_phrases_only_from_wording_prohibitions(rule: str, expected: list[str]) -> None:
    from app.agents.context import banned_phrases

    assert banned_phrases({"content_restrictions": [rule]}, None) == expected


# ---------- Timeline normalisation ----------


def test_normalize_timeline_hits_target_exactly() -> None:
    scenes = [
        SimpleNamespace(scene_number=0, duration_seconds=d, start_time=0, end_time=0)
        for d in (7, 7, 7)
    ]

    adjusted = normalize_timeline(scenes, 30)

    assert adjusted
    assert sum(s.duration_seconds for s in scenes) == pytest.approx(30)
    assert [(s.start_time, s.end_time) for s in scenes][0] == (0, 10)
    assert scenes[-1].end_time == 30 and [s.scene_number for s in scenes] == [1, 2, 3]


def test_normalize_timeline_leaves_correct_timings() -> None:
    scenes = [
        SimpleNamespace(scene_number=1, duration_seconds=d, start_time=0, end_time=0)
        for d in (10, 20)
    ]

    assert normalize_timeline(scenes, 30) is False
    assert [s.end_time for s in scenes] == [10, 30]
