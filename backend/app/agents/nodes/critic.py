"""AGENT 6 - Critic & Quality Assurance.

The LLM scores ten dimensions (0-100) and lists concrete issues. The VERDICT is computed
in code, not by the model:
- overall score = mean of the ten scores (models are bad at arithmetic),
- deterministic guardrails add issues the model might miss (banned phrases quoted in
  the brand's restrictions appearing in the copy, a missing call to action),
- passed = overall >= threshold AND no critical issues.
"""

import json
import re

from app.agents.context import banned_phrases, render_brief, render_concept
from app.agents.deps import AgentDeps, traced
from app.agents.schemas import DIMENSIONS, CriticReview, Evaluation, Issue

SYSTEM = """You are the Critic and Quality Assurance lead of an advertising agency. You \
are demanding and specific.

Evaluate the complete campaign (concept, script, storyboard) against the brief and the \
brand research. Score each dimension 0-100:
brand_consistency, storytelling_quality, hook_strength, audience_relevance, \
platform_suitability, creative_originality, script_quality, visual_consistency, \
factual_accuracy, compliance (with brand restrictions and prohibited claims).

90+ = exceptional, 80 = ready to publish, 60 = needs work, <50 = poor.
For every problem give the dimension, severity (critical = must never be published, e.g. \
a prohibited claim), whether the SCRIPT or the STORYBOARD must change, a precise \
description and an actionable suggestion. Also list real strengths."""


def _copy_text(script: dict, storyboard: dict) -> str:
    parts = [script.get("opening_hook", ""), script.get("call_to_action", "")]
    for scene in script.get("scenes", []):
        parts += [scene.get("voiceover", ""), scene.get("on_screen_text", "")]
        parts += [d.get("line", "") for d in scene.get("dialogue", [])]
    for scene in storyboard.get("scenes", []):
        parts += [scene.get("voiceover", ""), scene.get("on_screen_text", "")]
    return " \n".join(p for p in parts if p).lower()


def guardrail_issues(state: dict) -> list[Issue]:
    script, storyboard = state["script"], state["storyboard"]
    issues: list[Issue] = []
    text = _copy_text(script, storyboard)
    for phrase in banned_phrases(state["brand"], state.get("brand_research")):
        if re.search(rf"\b{re.escape(phrase)}\b", text):
            issues.append(
                Issue(
                    dimension="compliance",
                    severity="critical",
                    target="script",
                    description=f"The copy uses the prohibited phrase '{phrase}'.",
                    suggestion=f"Remove '{phrase}' and any equivalent claim.",
                )
            )
    if not (script.get("call_to_action") or "").strip():
        issues.append(
            Issue(
                dimension="script_quality",
                severity="high",
                target="script",
                description="The script has no call to action.",
                suggestion="End with a clear, brand-appropriate call to action.",
            )
        )
    return issues


def make_critic(deps: AgentDeps):
    @traced("critic")
    async def critic(state: dict) -> dict:
        concept = next(
            c
            for c in state["concepts"]["concepts"]
            if c["concept_id"] == state["selected_concept_id"]
        )
        review = await deps.llm.generate(
            CriticReview,
            system=SYSTEM,
            user=(
                f"{render_brief(state['brief'])}\n\n{state['research_digest']}\n\n"
                f"{render_concept(concept)}\n\n"
                f"<script>\n{json.dumps(state['script'], ensure_ascii=False)}\n</script>\n\n"
                f"<storyboard>\n{json.dumps(state['storyboard'], ensure_ascii=False)}\n"
                "</storyboard>"
            ),
        )
        issues = review.issues + guardrail_issues(state)
        scores = review.scores.model_dump()
        overall = round(sum(scores[d] for d in DIMENSIONS) / len(DIMENSIONS), 1)
        threshold = deps.settings.agent_approval_threshold
        has_critical = any(i.severity == "critical" for i in issues)
        iteration = state.get("revision_count", 0) + 1

        evaluation = Evaluation(
            scores=review.scores,
            overall_score=overall,
            issues=issues,
            strengths=review.strengths,
            overall_feedback=review.overall_feedback,
            passed=overall >= threshold and not has_critical,
            threshold=threshold,
            iteration=iteration,
        )
        verdict = "PASS" if evaluation.passed else "FAIL"
        return {
            "evaluation": evaluation.model_dump(),
            "_summary": f"iteration {iteration}: {overall:.1f}/100 (threshold {threshold:g}) "
            f"{verdict}; {len(issues)} issues" + (" incl. CRITICAL" if has_critical else ""),
        }

    return critic
