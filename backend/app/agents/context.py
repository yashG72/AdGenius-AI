"""Shared prompt building blocks: brief, brand profile, research digest, concept.

Keeping these in one place means every agent sees the same facts phrased the same way.
"""

import json
import re
from typing import Any

from app.models import Brand


def brand_snapshot(brand: Brand) -> dict[str, Any]:
    """Trusted copy of the brand profile stored in the run state (and its checkpoints)."""
    return {
        "id": str(brand.id),
        "organization_id": str(brand.organization_id),
        "name": brand.name,
        "description": brand.description,
        "industry": brand.industry,
        "website": brand.website,
        "product_information": brand.product_information,
        "target_audience": brand.target_audience,
        "brand_personality": brand.brand_personality,
        "brand_voice": brand.brand_voice,
        "positioning": brand.positioning,
        "messaging": brand.messaging,
        "brand_colors": brand.brand_colors,
        "marketing_objectives": brand.marketing_objectives,
        "content_restrictions": brand.content_restrictions,
        "competitors": brand.competitors,
        "social_links": brand.social_links,
    }


def _lines(pairs: list[tuple[str, Any]]) -> str:
    out = []
    for label, value in pairs:
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            value = "; ".join(v if isinstance(v, str) else json.dumps(v) for v in value)
        out.append(f"{label}: {value}")
    return "\n".join(out)


def render_brief(brief: dict[str, Any]) -> str:
    return (
        "<brief>\n"
        + _lines(
            [
                ("Campaign name", brief.get("campaign_name")),
                ("Objective", brief.get("objective")),
                ("Marketing objective", brief.get("marketing_objective")),
                ("Product", brief.get("product_description")),
                ("Target audience", brief.get("target_audience")),
                ("Platform", brief.get("platform")),
                ("Duration (seconds)", brief.get("duration_seconds")),
                ("Video format (aspect ratio)", brief.get("video_format")),
                ("Language", brief.get("language")),
                ("Tone", brief.get("tone")),
                ("Budget", brief.get("budget")),
                ("Additional requirements", brief.get("additional_requirements")),
            ]
        )
        + "\n</brief>"
    )


def render_brand_profile(brand: dict[str, Any]) -> str:
    colors = [f"{c.get('name')} {c.get('hex')}" for c in brand.get("brand_colors") or []]
    competitors = [c.get("name") for c in brand.get("competitors") or [] if c.get("name")]
    return (
        "<brand_profile>\n"
        + _lines(
            [
                ("Brand", brand.get("name")),
                ("Industry", brand.get("industry")),
                ("Description", brand.get("description")),
                ("Products", brand.get("product_information")),
                ("Target audience", brand.get("target_audience")),
                ("Personality", brand.get("brand_personality")),
                ("Voice", brand.get("brand_voice")),
                ("Positioning", brand.get("positioning")),
                ("Messaging", brand.get("messaging")),
                ("Colours", colors),
                ("Marketing objectives", brand.get("marketing_objectives")),
                ("Content restrictions", brand.get("content_restrictions")),
                ("Known competitors", competitors),
            ]
        )
        + "\n</brand_profile>"
    )


def research_digest(brand_research: dict | None, competitor: dict | None) -> str:
    """Compact research summary handed to the creative agents."""
    parts = []
    if brand_research:
        parts.append(
            "<brand_research>\n"
            + _lines(
                [
                    ("Summary", brand_research.get("summary")),
                    ("Products", brand_research.get("products")),
                    ("Target audience", brand_research.get("target_audience")),
                    ("Personality", brand_research.get("brand_personality")),
                    ("Tone of voice", brand_research.get("tone_of_voice")),
                    ("Positioning", brand_research.get("positioning")),
                    ("Key messages", brand_research.get("key_messages")),
                    ("PROHIBITED claims / messaging", brand_research.get("prohibited_claims")),
                    ("Visual guidelines", brand_research.get("visual_guidelines")),
                    ("Past campaign learnings", brand_research.get("past_campaign_learnings")),
                ]
            )
            + "\n</brand_research>"
        )
    if competitor:
        competitors = [
            f"{c['name']} - positioning: {c['positioning']}; messaging: {c['messaging']}"
            for c in competitor.get("competitors", [])
        ]
        parts.append(
            "<competitor_research>\n"
            + _lines(
                [
                    ("Summary", competitor.get("summary")),
                    ("Competitors", competitors),
                    ("Market trends", [t["trend"] for t in competitor.get("market_trends", [])]),
                    (
                        "Opportunities",
                        [o["opportunity"] for o in competitor.get("opportunities", [])],
                    ),
                ]
            )
            + "\n</competitor_research>"
        )
    return "\n\n".join(parts) or "(no research available)"


def render_concept(concept: dict[str, Any]) -> str:
    return (
        "<selected_concept>\n"
        + _lines(
            [
                ("Title", concept.get("title")),
                ("Core idea", concept.get("core_idea")),
                ("Creative angle", concept.get("creative_angle")),
                ("Target emotion", concept.get("target_emotion")),
                ("Opening hook", concept.get("opening_hook")),
                ("Storytelling approach", concept.get("storytelling_approach")),
                ("Key message", concept.get("key_message")),
                ("USP", concept.get("unique_selling_proposition")),
                ("Call to action", concept.get("call_to_action")),
            ]
        )
        + "\n</selected_concept>"
    )


_QUOTED = re.compile(r"[\"'‘’“”]([^\"'‘’“”]{2,40})[\"'‘’“”]")


# A quoted phrase is banned only when the rule forbids SAYING/USING it. A rule like
# "Do not modify the tagline 'Fizz Without the Fall'" quotes a REQUIRED phrase.
_PROHIBITS_WORDING = re.compile(
    r"\b(never|not|don't|avoid|no)\b[^.;]*?\b(say|said|use|used|write|mention|call|"
    r"describe[ds]?|claim|words?|phrases?|terms?)\b",
    re.IGNORECASE,
)


def _spelling_key(phrase: str) -> str:
    """'BrewNest', 'Brew Nest' and 'brewnest' share one key: they differ only in spelling."""
    return re.sub(r"[\s\-_]+", "", phrase).lower()


def banned_phrases(brand: dict[str, Any], brand_research: dict | None) -> list[str]:
    """Literal phrases quoted inside wording prohibitions, e.g. Never say 'healthy'.

    Used for a deterministic compliance check that does not rely on the LLM noticing.
    The check matches case-insensitively, so three kinds of quoted phrase are NOT banned:
    - phrases quoted before the prohibition ('always written "Brewnest" - never ...');
    - spelling rules: phrases differing only in case/spacing ('"Brewnest", never
      "BrewNest"') - a case-insensitive match would flag the CORRECT spelling; the LLM
      critic still reviews spelling;
    - the brand's own name, as a last safety net.
    """
    rules = list(brand.get("content_restrictions") or [])
    rules += list((brand_research or {}).get("prohibited_claims") or [])
    brand_key = _spelling_key(brand.get("name") or "")
    found: set[str] = set()
    for rule in rules:
        prohibition = _PROHIBITS_WORDING.search(rule)
        if not prohibition:
            continue
        quoted = [m.group(1).strip() for m in _QUOTED.finditer(rule)]
        keys = [_spelling_key(q) for q in quoted]
        spelling_variants = {k for k in keys if keys.count(k) > 1}
        for match in _QUOTED.finditer(rule):
            phrase, key = match.group(1).strip(), _spelling_key(match.group(1))
            if match.start() < prohibition.start():
                continue  # quoted before "never ...": the required form, not the banned one
            if key in spelling_variants or (brand_key and key == brand_key):
                continue
            found.add(phrase.lower())
    return sorted(p for p in found if p)
