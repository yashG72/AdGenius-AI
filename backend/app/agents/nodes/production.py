"""AGENT 5 - Scriptwriter and Visual Director (two production stages).

Both agents receive the Critic's issues on a revision round and must fix exactly those.
Timings are normalised deterministically afterwards so the total ALWAYS equals the
requested duration, and every image prompt gets the brief's aspect ratio.
"""

import json

from app.agents.context import render_brief, render_concept
from app.agents.deps import AgentDeps, traced
from app.agents.schemas import Script, Storyboard
from app.agents.timing import normalize_timeline

SCRIPT_SYSTEM = """You are an expert advertising Scriptwriter.

Write the complete script for the selected concept: an opening hook in the first 2-3 \
seconds, scene-by-scene voiceover / dialogue / on-screen text / sound cues, natural \
transitions, and a clear call to action at the end. The scene durations must add up to \
the requested total duration. Write in the requested language. Match the brand's tone \
of voice exactly and never use any prohibited claim or wording."""

STORYBOARD_SYSTEM = """You are the Visual Director of an advertising production.

Convert the approved script into a shot-by-shot storyboard. For every scene define the \
visual composition, camera angle, camera movement, lighting/atmosphere, transition, and \
a detailed, self-contained text-to-image prompt (subject, environment, lighting, \
composition, camera perspective, style) plus a negative prompt. Keep characters, \
wardrobe, colour palette and props IDENTICAL across scenes - describe them fully in \
every prompt, because each image is generated independently. Follow the brand's visual \
guidelines and colours. Scene durations must add up to the requested total duration."""


def _selected_concept(state: dict) -> dict:
    wanted = state["selected_concept_id"]
    return next(c for c in state["concepts"]["concepts"] if c["concept_id"] == wanted)


def _brand_rules(state: dict) -> str:
    research = state.get("brand_research") or {}
    brand = state["brand"]
    colors = [f"{c.get('name')} {c.get('hex')}" for c in brand.get("brand_colors") or []]
    rules = {
        "tone_of_voice": research.get("tone_of_voice") or brand.get("brand_voice"),
        "personality": research.get("brand_personality") or brand.get("brand_personality"),
        "prohibited": (research.get("prohibited_claims") or [])
        + (brand.get("content_restrictions") or []),
        "visual_guidelines": research.get("visual_guidelines"),
        "brand_colours": colors,
    }
    return "<brand_rules>\n" + json.dumps(rules, indent=1, ensure_ascii=False) + "\n</brand_rules>"


def _revision_notes(state: dict, target: str, previous_key: str) -> str:
    issues = [i for i in state.get("revision_feedback") or [] if i["target"] == target]
    previous = state.get(previous_key)
    if not issues or not previous:
        return ""
    notes = "\n".join(
        f"- [{i['severity']}] {i['description']} -> {i['suggestion']}" for i in issues
    )
    return (
        f"\n\n<revision_request>\nThe Critic rejected the previous version. Previous version:\n"
        f"{json.dumps(previous, ensure_ascii=False)[:6000]}\n\nFix these issues:\n{notes}\n"
        "</revision_request>"
    )


def make_scriptwriter(deps: AgentDeps):
    @traced("scriptwriter")
    async def scriptwriter(state: dict) -> dict:
        brief = state["brief"]
        target = float(brief["duration_seconds"])
        script = await deps.llm.generate(
            Script,
            system=SCRIPT_SYSTEM,
            user=f"{render_brief(brief)}\n\n{render_concept(_selected_concept(state))}\n\n"
            f"{_brand_rules(state)}" + _revision_notes(state, "script", "script"),
        )
        script.timing_adjusted = normalize_timeline(script.scenes, target)
        script.duration_seconds = target
        revising = bool(state.get("revision_count"))
        return {
            "script": script.model_dump(),
            "_summary": f"{'revised ' if revising else ''}script '{script.title}': "
            f"{len(script.scenes)} scenes, {target:g}s"
            + (" (timings normalised)" if script.timing_adjusted else ""),
        }

    return scriptwriter


def make_visual_director(deps: AgentDeps):
    @traced("visual_director")
    async def visual_director(state: dict) -> dict:
        brief = state["brief"]
        target = float(brief["duration_seconds"])
        storyboard = await deps.llm.generate(
            Storyboard,
            system=STORYBOARD_SYSTEM,
            user=f"{render_brief(brief)}\n\n{render_concept(_selected_concept(state))}\n\n"
            f"<script>\n{json.dumps(state['script'], ensure_ascii=False)}\n</script>\n\n"
            f"{_brand_rules(state)}" + _revision_notes(state, "storyboard", "storyboard"),
        )
        storyboard.timing_adjusted = normalize_timeline(storyboard.scenes, target)
        storyboard.total_duration_seconds = target
        for scene in storyboard.scenes:
            scene.image_prompt.aspect_ratio = brief["video_format"]  # never trust the model here
        return {
            "storyboard": storyboard.model_dump(),
            "_summary": f"{len(storyboard.scenes)} storyboard scenes with image prompts "
            f"({brief['video_format']})"
            + (" (timings normalised)" if storyboard.timing_adjusted else ""),
        }

    return visual_director
