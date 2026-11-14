"""Run the multi-agent campaign workflow from the command line (dev/admin tool).

Phase 8 exposes the same workflow through the REST API and the Celery worker. From
backend/ with PostgreSQL, Redis and Qdrant running:

    python -m scripts.run_campaign start --brand-id <uuid> --brief scripts/examples/mano_brief.json
    python -m scripts.run_campaign start ... --auto-approve        # take the recommended concept
    python -m scripts.run_campaign resume --thread <id> --approve C2
    python -m scripts.run_campaign resume --thread <id> --reject "funnier, less product talk"
    python -m scripts.run_campaign retry --thread <id>             # after a failure
    python -m scripts.run_campaign show --thread <id> [--out result.json]

Runs are durable: `start` can pause at concept approval, and `resume` continues it
later from the PostgreSQL checkpoint, even from a different process.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

from app.agents.checkpointer import postgres_checkpointer
from app.agents.context import brand_snapshot
from app.agents.factory import live_agent_deps
from app.agents.nodes.approval import ConceptDecision
from app.agents.runner import CampaignWorkflow, RunView
from app.agents.schemas import CampaignBrief
from app.core.aio import run_async
from app.core.config import get_settings
from app.core.tracing import configure_tracing
from app.db.session import SessionFactory, engine
from app.models import Brand


def print_view(view: RunView) -> None:
    values = view.values
    print(f"\nthread: {view.thread_id}\nstatus: {view.status.upper()}")
    print("\nexecution trace:")
    for e in values.get("events", []):
        print(f"  {e['agent']:20} {e['status']:9} {e['duration_ms'] / 1000:6.1f}s  {e['summary']}")

    if view.pending_approval:
        p = view.pending_approval
        print(f"\nCONCEPTS (round {p['round']}) - recommended: {p['recommended_concept_id']}")
        for c in p["concepts"]:
            print(
                f"\n  [{c['concept_id']}] {c['title']}\n      idea: {c['core_idea']}"
                f"\n      hook: {c['opening_hook']}\n      emotion: {c['target_emotion']}"
                f" | CTA: {c['call_to_action']}"
            )
        print(f"\n  why {p['recommended_concept_id']}: {p['recommendation_reasoning']}")

    final = values.get("final")
    if final and final.get("evaluation"):
        ev = final["evaluation"]
        print(
            f"\nCRITIC: {ev['overall_score']:.1f}/100 (threshold {ev['threshold']:g}) -> "
            f"{'PASS' if ev['passed'] else 'FAIL'} after {len(final['revision_history'])} "
            "revision(s)"
        )
        print("  scores: " + ", ".join(f"{k}={v}" for k, v in ev["scores"].items()))
        for issue in ev["issues"]:
            print(f"  - [{issue['severity']}/{issue['target']}] {issue['description']}")
        script = final["script"]
        print(f"\nSCRIPT: {script['title']} ({script['duration_seconds']:g}s)")
        for s in script["scenes"]:
            print(
                f"  {s['start_time']:>4}-{s['end_time']:<4}s  VO: {s['voiceover'][:90]}"
                + (f"  | TEXT: {s['on_screen_text'][:40]}" if s["on_screen_text"] else "")
            )
        first = final["image_prompts"][0]
        print(
            f"\nIMAGE PROMPT (scene 1, {first['aspect_ratio']}):\n  {first['prompt'][:400]}"
            f"\n  negative: {first['negative_prompt'][:150]}"
        )


async def main(args: argparse.Namespace) -> dict | None:
    settings = get_settings()
    configure_tracing(settings)
    try:
        async with (
            SessionFactory() as session,
            SessionFactory() as knowledge_session,
            postgres_checkpointer(settings.database_url) as saver,
            live_agent_deps(knowledge_session, settings) as deps,
        ):
            workflow = CampaignWorkflow(deps, saver)
            if args.command == "start":
                brand = await session.get(Brand, uuid.UUID(args.brand_id))
                if brand is None or brand.deleted_at is not None:
                    sys.exit("Brand not found.")
                brief = CampaignBrief.model_validate({**args.brief_data, "brand_id": args.brand_id})
                thread = args.thread or str(uuid.uuid4())
                print(f"starting run {thread} for brand {brand.name} ...")
                view = await workflow.start(thread, brief, brand_snapshot(brand))
                approve = (
                    view.pending_approval["recommended_concept_id"]
                    if args.auto_approve and view.pending_approval
                    else args.approve
                )
                if approve and view.status == "awaiting_concept_approval":
                    print_view(view)
                    print(f"\napproving {approve} and producing the campaign ...")
                    view = await workflow.resume(
                        thread, ConceptDecision(action="approve", concept_id=approve)
                    )
            elif args.command == "resume":
                decision = (
                    ConceptDecision(action="approve", concept_id=args.approve)
                    if args.approve
                    else ConceptDecision(action="reject", feedback=args.reject)
                )
                view = await workflow.resume(args.thread, decision)
            elif args.command == "retry":
                print(f"retrying run {args.thread} from its last checkpoint ...")
                view = await workflow.retry(args.thread)
            else:
                view = await workflow.view(args.thread)

            print_view(view)
            return view.values.get("final")
    finally:
        await engine.dispose()


def cli() -> None:
    parser = argparse.ArgumentParser(description="Run the AdGenius campaign workflow.")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--brand-id", required=True)
    start.add_argument("--brief", required=True, help="JSON file (see scripts/examples/)")
    start.add_argument("--thread", help="run/thread id (default: new UUID)")
    group = start.add_mutually_exclusive_group()
    group.add_argument("--auto-approve", action="store_true", help="approve recommended concept")
    group.add_argument("--approve", help="concept id to approve, e.g. C2")
    resume = sub.add_parser("resume")
    resume.add_argument("--thread", required=True)
    decision = resume.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve")
    decision.add_argument("--reject", help="feedback for the strategist")
    retry = sub.add_parser("retry", help="continue a failed run from its last checkpoint")
    retry.add_argument("--thread", required=True)
    show = sub.add_parser("show")
    show.add_argument("--thread", required=True)
    for p in (start, resume, retry, show):
        p.add_argument("--out", help="write the final campaign JSON here")
    args = parser.parse_args()
    if args.command == "start":  # file I/O stays out of the async code
        args.brief_data = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    final = run_async(main(args))
    if args.out and final:
        Path(args.out).write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nfull campaign written to {args.out}")


if __name__ == "__main__":
    cli()
