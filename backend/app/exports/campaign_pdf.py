"""Campaign PDF export.

HTML + CSS -> PDF with PyMuPDF's Story renderer (already a dependency; no GTK/Chrome
needed, unlike WeasyPrint or headless browsers). Sections follow the spec's campaign
outputs: research report, creative strategy, script, storyboard with image prompts,
quality evaluation and sources.

Every value is HTML-escaped: concepts, scripts and web snippets come from LLMs and
the internet, so they are treated as untrusted text, never as markup.
"""

import io
from datetime import datetime
from html import escape
from typing import Any

import pymupdf

ACCENT = "#B36B00"

CSS = f"""
body {{ font-family: sans-serif; font-size: 9.5px; color: #1f1f1f; line-height: 1.35; }}
h1 {{ font-size: 22px; color: {ACCENT}; margin: 0 0 4px 0; }}
h2 {{ font-size: 14px; color: {ACCENT}; border-bottom: 1px solid #e3c79b;
     margin: 16px 0 6px 0; padding-bottom: 2px; }}
h3 {{ font-size: 11px; margin: 10px 0 3px 0; }}
p {{ margin: 2px 0 5px 0; }}
.muted {{ color: #6b6b6b; }}
.tag {{ color: {ACCENT}; font-weight: bold; }}
table {{ border-collapse: collapse; width: 100%; margin: 4px 0 8px 0; }}
th {{ text-align: left; color: {ACCENT}; border-bottom: 2px solid #e3c79b; }}
td, th {{ border: 1px solid #d9d9d9; padding: 3px 4px; vertical-align: top; }}
.box {{ border-left: 3px solid #e3c79b; padding: 2px 0 2px 8px; margin: 6px 0; }}
ul {{ margin: 2px 0 6px 0; }}
"""


def _e(value: Any) -> str:
    """Escape anything for HTML ('' for missing values)."""
    if value is None:
        return ""
    if isinstance(value, float):
        value = f"{value:g}"
    return escape(str(value))


def _list(items: list[Any] | None) -> str:
    items = [i for i in items or [] if i]
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>" if items else ""


def _field(label: str, value: Any) -> str:
    return f"<p><b>{_e(label)}:</b> {_e(value)}</p>" if value not in (None, "", []) else ""


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


# ---------- sections ----------


def _cover(ctx: dict[str, Any]) -> str:
    brief, run = ctx["brief"], ctx["run"]
    score = f"{run['overall_score']:.1f}/100" if run.get("overall_score") is not None else "n/a"
    rows = [
        ["Brand", ctx["brand_name"]],
        ["Objective", brief.get("objective")],
        ["Target audience", brief.get("target_audience")],
        ["Platform / format", f"{brief.get('platform')} · {brief.get('video_format')}"],
        ["Duration", f"{brief.get('duration_seconds')} seconds"],
        ["Tone", brief.get("tone")],
        ["Language", brief.get("language")],
    ]
    return (
        f"<h1>{_e(ctx['campaign_name'])}</h1>"
        f"<p class='muted'>Run v{_e(run['version'])} · status <span class='tag'>"
        f"{_e(run['status'])}</span> · quality score {_e(score)} · exported "
        f"{_e(ctx['exported_at'])}</p>" + _table(["Brief", ""], [r for r in rows if r[1]])
    )


def _research(final: dict[str, Any]) -> str:
    report = final.get("research_report") or {}
    brand = report.get("brand") or {}
    out = ["<h2>1. Research report</h2>", "<h3>Brand</h3>", f"<p>{_e(brand.get('summary'))}</p>"]
    for label, key in [
        ("Products", "products"),
        ("Target audience", "target_audience"),
        ("Personality", "brand_personality"),
        ("Tone of voice", "tone_of_voice"),
        ("Positioning", "positioning"),
        ("Visual guidelines", "visual_guidelines"),
    ]:
        out.append(_field(label, brand.get(key)))
    if brand.get("key_messages"):
        out.append("<p><b>Key messages</b></p>" + _list(brand["key_messages"]))
    if brand.get("prohibited_claims"):
        out.append("<p><b>Prohibited claims</b></p>" + _list(brand["prohibited_claims"]))
    if brand.get("knowledge_gaps"):
        out.append("<p><b>Knowledge gaps</b></p>" + _list(brand["knowledge_gaps"]))

    competitors = report.get("competitors") or {}
    if competitors:
        out.append("<h3>Competitors &amp; market</h3>")
        out.append(f"<p>{_e(competitors.get('summary'))}</p>")
        rows = [
            [c["name"], c["positioning"], c["messaging"], ", ".join(c.get("sources", []))]
            for c in competitors.get("competitors", [])
        ]
        if rows:
            out.append(_table(["Competitor", "Positioning", "Messaging", "Sources"], rows))
        trends = [
            f"{t['trend']} [{', '.join(t['sources'])}]"
            for t in competitors.get("market_trends", [])
        ]
        if trends:
            out.append("<p><b>Market trends</b></p>" + _list(trends))
        opportunities = [
            f"{o['opportunity']} — {o['rationale']}"
            + ("" if o.get("evidence_backed") else " (strategic inference)")
            for o in competitors.get("opportunities", [])
        ]
        if opportunities:
            out.append("<p><b>Opportunities</b></p>" + _list(opportunities))
    return "".join(out)


def _strategy(final: dict[str, Any]) -> str:
    strategy = final.get("creative_strategy") or {}
    selected = strategy.get("selected_concept_id")
    out = [
        "<h2>2. Creative strategy</h2>",
        _field("Core messaging", strategy.get("campaign_messaging")),
    ]
    for c in strategy.get("concepts", []):
        chosen = c["concept_id"] == selected
        out.append(
            f"<div class='box'><h3>{_e(c['concept_id'])} · {_e(c['title'])}"
            + (" <span class='tag'>(SELECTED)</span>" if chosen else "")
            + "</h3>"
            + _field("Core idea", c.get("core_idea"))
            + _field("Creative angle", c.get("creative_angle"))
            + _field("Opening hook", c.get("opening_hook"))
            + _field("Storytelling", c.get("storytelling_approach"))
            + _field("Target emotion", c.get("target_emotion"))
            + _field("Key message", c.get("key_message"))
            + _field("USP", c.get("unique_selling_proposition"))
            + _field("Call to action", c.get("call_to_action"))
            + _field("Reasoning", c.get("reasoning"))
            + "</div>"
        )
    if strategy.get("recommendation_reasoning"):
        out.append(
            _field(
                f"Strategist recommendation ({strategy.get('recommended_concept_id')})",
                strategy["recommendation_reasoning"],
            )
        )
    return "".join(out)


def _script(final: dict[str, Any]) -> str:
    script = final.get("script")
    if not script:
        return ""
    rows = []
    for s in script.get("scenes", []):
        dialogue = " / ".join(f"{d['speaker']}: {d['line']}" for d in s.get("dialogue", []))
        rows.append(
            [
                f"{s['start_time']:g}–{s['end_time']:g}s",
                s.get("visual_summary"),
                " ".join(p for p in [s.get("voiceover"), dialogue] if p),
                s.get("on_screen_text"),
                s.get("sound"),
            ]
        )
    return (
        f"<h2>3. Script — {_e(script.get('title'))}</h2>"
        + _field("Duration", f"{script.get('duration_seconds'):g} seconds")
        + _field("Opening hook", script.get("opening_hook"))
        + _table(["Time", "Visual", "Voiceover / dialogue", "On-screen text", "Sound"], rows)
        + _field("Music", script.get("music_suggestion"))
        + _field("Call to action", script.get("call_to_action"))
    )


def _storyboard(final: dict[str, Any]) -> str:
    board = final.get("storyboard")
    if not board:
        return ""
    out = [
        "<h2>4. Storyboard &amp; image prompts</h2>",
        _field("Visual style", board.get("visual_style")),
        _field("Consistency notes", board.get("consistency_notes")),
    ]
    for s in board.get("scenes", []):
        prompt = s.get("image_prompt", {})
        out.append(
            f"<div class='box'><h3>Scene {_e(s['scene_number'])} · "
            f"{s['start_time']:g}–{s['end_time']:g}s</h3>"
            + _field("Description", s.get("scene_description"))
            + _field("Visual direction", s.get("visual_direction"))
            + _field("Composition", s.get("composition"))
            + _field(
                "Camera",
                f"{s.get('camera_angle')} · {s.get('camera_movement')}",
            )
            + _field("Lighting", s.get("lighting"))
            + _field("Voiceover", s.get("voiceover"))
            + _field("On-screen text", s.get("on_screen_text"))
            + _field("Transition", s.get("transition"))
            + _field(f"Image prompt ({prompt.get('aspect_ratio')})", prompt.get("prompt"))
            + _field("Negative prompt", prompt.get("negative_prompt"))
            + "</div>"
        )
    return "".join(out)


def _evaluation(final: dict[str, Any]) -> str:
    ev = final.get("evaluation")
    if not ev:
        return ""
    verdict = "PASSED" if ev["passed"] else "BELOW THRESHOLD — needs human review"
    scores = [[k.replace("_", " ").capitalize(), v] for k, v in ev["scores"].items()]
    issues = [
        [i["severity"], i["target"], i["dimension"], i["description"], i["suggestion"]]
        for i in ev.get("issues", [])
    ]
    history = [
        [h["iteration"], f"{h['overall_score']:.1f}", len(h["issues"]), h["routed_to"]]
        for h in final.get("revision_history", [])
    ]
    return (
        "<h2>5. Quality evaluation</h2>"
        f"<p><b>Overall: {ev['overall_score']:.1f}/100</b> (threshold {ev['threshold']:g}) · "
        f"<span class='tag'>{_e(verdict)}</span></p>"
        + _table(["Dimension", "Score"], scores)
        + (
            _table(["Severity", "Fix in", "Dimension", "Issue", "Suggestion"], issues)
            if issues
            else ""
        )
        + ("<p><b>Strengths</b></p>" + _list(ev.get("strengths")) if ev.get("strengths") else "")
        + _field("Critic summary", ev.get("overall_feedback"))
        + (
            "<h3>Revision history</h3>"
            + _table(["Revision", "Score before", "Issues", "Sent to"], history)
            if history
            else "<p class='muted'>Approved without revisions.</p>"
        )
    )


def _sources(final: dict[str, Any]) -> str:
    report = final.get("research_report") or {}
    docs = [
        [
            f"[{s['source']}]",
            s["original_filename"],
            s.get("source_page") or "–",
            s["excerpt"][:160],
        ]
        for s in report.get("brand_sources", [])
        if s.get("cited")
    ]
    web = [
        [s["id"], s["title"], s["url"], s["retrieved_at"][:10]]
        for s in (report.get("competitors") or {}).get("sources", [])
        if s.get("cited")
    ]
    if not docs and not web:
        return ""
    return (
        "<h2>6. Sources</h2>"
        + (
            "<h3>Brand documents</h3>" + _table(["#", "Document", "Page", "Excerpt"], docs)
            if docs
            else ""
        )
        + ("<h3>Web sources</h3>" + _table(["#", "Title", "URL", "Retrieved"], web) if web else "")
    )


def build_html(ctx: dict[str, Any]) -> str:
    ctx = {**ctx, "exported_at": ctx.get("exported_at") or datetime.now().strftime("%Y-%m-%d")}
    final = ctx["final"]
    return "".join(
        [
            _cover(ctx),
            _research(final),
            _strategy(final),
            _script(final),
            _storyboard(final),
            _evaluation(final),
            _sources(final),
        ]
    )


def render_pdf(ctx: dict[str, Any]) -> bytes:
    """ctx: campaign_name, brand_name, run{version,status,overall_score}, brief, final."""
    story = pymupdf.Story(html=build_html(ctx), user_css=CSS)
    raw = io.BytesIO()
    writer = pymupdf.DocumentWriter(raw)
    page = pymupdf.paper_rect("a4")
    content = page + (42, 42, -42, -48)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(content)
        story.draw(device)
        writer.end_page()
    writer.close()

    # Second pass: footer with page numbers, document metadata, smaller file.
    doc = pymupdf.open(stream=raw.getvalue(), filetype="pdf")
    footer = f"AdGenius AI · {ctx['campaign_name']} · run v{ctx['run']['version']}"
    for number, pdf_page in enumerate(doc, start=1):
        pdf_page.insert_text(
            (42, page.height - 24), footer[:110], fontsize=7, color=(0.45, 0.45, 0.45)
        )
        pdf_page.insert_text(
            (page.width - 90, page.height - 24),
            f"Page {number} of {doc.page_count}",
            fontsize=7,
            color=(0.45, 0.45, 0.45),
        )
    doc.set_metadata(
        {
            "title": ctx["campaign_name"],
            "author": "AdGenius AI",
            "subject": f"{ctx['brand_name']} campaign",
        }
    )
    doc.subset_fonts()  # embed only the glyphs actually used
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data
