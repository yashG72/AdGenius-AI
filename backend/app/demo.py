"""Public demo: a shared, read-only account with a finished sample campaign.

Recruiters and other visitors click "Try the demo" and land in a workspace that already
contains the Brewnest brand, its knowledge base and a completed campaign - no sign-up and
no 5-minute wait for the agents.

- `ensure_demo()` runs in the background at API startup (DEMO_ENABLED=true). It is
  idempotent: each step checks what already exists, so restarts only finish missing work.
  The campaign is produced by the REAL agent workflow; the concept is approved
  automatically, exactly as a user would click "Approve".
- `demo_blocks_request()` makes the account read-only: browsing, PDF export and asking the
  knowledge base work; anything that changes data (or starts paid agent runs) is refused.
- The account's password is random and never stored anywhere, so the only way in is the
  `/auth/demo` endpoint.
"""

import asyncio
import io
import logging
import secrets
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.schemas import BriefFields
from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.core.storage import get_storage
from app.models import (
    Brand,
    BrandDocument,
    Campaign,
    CampaignRun,
    DocumentStatus,
    DocumentType,
    Membership,
    RunStatus,
    User,
)
from app.schemas.brand import BrandCreate
from app.schemas.campaign import CampaignCreate
from app.schemas.organization import OrganizationCreate

logger = logging.getLogger(__name__)

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples" / "brewnest"
DEMO_ORG_NAME = "Brewnest (Demo)"
DEMO_BRAND_NAME = "Brewnest"
DEMO_CAMPAIGN_NAME = "Mango Tonic Summer Launch"
MAX_DEMO_RUN_ATTEMPTS = 3  # never loop forever spending LLM credits
POLL_SECONDS = 5

DOCUMENTS: dict[str, DocumentType] = {
    "brewnest_brand_guidelines.pdf": DocumentType.BRAND_GUIDELINES,
    "brewnest_legal_compliance.docx": DocumentType.OTHER,
    "brewnest_products.csv": DocumentType.PRODUCT_CATALOGUE,
    "brewnest_customer_personas.txt": DocumentType.CUSTOMER_PERSONA,
}

BRAND = {
    "name": DEMO_BRAND_NAME,
    "industry": "Ready-to-drink coffee",
    "description": "Ready-to-drink cold brew coffee in cans, "
    "slow-brewed for 18 hours in Bengaluru.",
    "target_audience": "Students and young professionals aged 19-28 in Indian cities",
    "brand_voice": "Smart, warm and quietly confident; playful but never sarcastic",
    "positioning": "Cafe-quality cold brew at half the cafe price",
    "brand_colors": [
        {"name": "Nest Brown", "hex": "#4A2C21"},
        {"name": "Cream", "hex": "#F3E9DC"},
        {"name": "Signal Orange", "hex": "#FF7A1A"},
    ],
    "content_restrictions": [
        "Never say 'healthy', 'guilt-free' or 'boosts immunity'",
        "Never show people drinking Brewnest while driving",
    ],
    "competitors": [{"name": "Sleepy Owl"}, {"name": "Starbucks Doubleshot"}],
}

BRIEF = BriefFields(
    objective="Launch the limited-edition Mango Tonic and get students to try it this summer",
    marketing_objective="Trial - 50,000 cans sold in the first 6 weeks",
    product_description="Brewnest Mango Tonic - cold brew with mango and sparkling tonic, "
    "250 ml can, Rs 150",
    target_audience="College students aged 19-23 in Bengaluru, Pune and Hyderabad",
    platform="instagram",
    video_format="9:16",
    duration_seconds=30,
    language="English",
    tone="Playful, sunny, a little cheeky",
    num_concepts=3,
    budget="Rs 8 lakh",
    additional_requirements="Show friends sharing cans; end on the tagline; "
    "include the caffeine disclaimer",
    competitor_research=True,
    competitor_focus="summer coffee drinks for students",
)


# ---------- Read-only rule ----------

# Writes the demo may still do: asking the knowledge base (rate-limited per user).
_DEMO_ALLOWED_WRITES = ("/knowledge/search", "/knowledge/ask")
_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def is_demo_user(user: User, settings: Settings) -> bool:
    return settings.demo_enabled and user.email == settings.demo_email


def demo_blocks_request(method: str, path: str) -> bool:
    if method.upper() in _SAFE_METHODS:
        return False
    return not path.rstrip("/").endswith(_DEMO_ALLOWED_WRITES)


async def get_demo_user(session: AsyncSession, settings: Settings) -> User | None:
    return await session.scalar(select(User).where(User.email == settings.demo_email))


async def demo_ready(session: AsyncSession, user: User) -> bool:
    """True once the demo workspace has a finished campaign to show."""
    finished = await session.scalar(
        select(CampaignRun.id)
        .join(Campaign, Campaign.id == CampaignRun.campaign_id)
        .join(Membership, Membership.organization_id == Campaign.organization_id)
        .where(
            Membership.user_id == user.id,
            CampaignRun.status.in_([RunStatus.COMPLETED, RunStatus.NEEDS_REVIEW]),
        )
        .limit(1)
    )
    return finished is not None


# ---------- Seeding ----------


async def ensure_demo(engine: AsyncEngine) -> None:
    """Create (or finish creating) the demo workspace. Safe to run on every startup."""
    from app.services import (
        brand_service,
        campaign_service,
        document_service,
        organization_service,
    )
    from app.worker import dispatch

    settings = get_settings()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    if not SAMPLES_DIR.is_dir():
        logger.warning("Demo: sample documents not found at %s", SAMPLES_DIR)

    async with sessions() as session:
        user = await get_demo_user(session, settings)
        if user is None:
            user = User(
                email=settings.demo_email,
                # Random and discarded: nobody can sign in with a password.
                password_hash=hash_password(secrets.token_urlsafe(48)),
                full_name="Demo Visitor",
            )
            session.add(user)
            await session.commit()
            logger.info("Demo: created the demo user")

        organizations = await organization_service.list_user_organizations(session, user.id)
        if organizations:
            organization = organizations[0][0]
        else:
            organization = await organization_service.create_organization(
                session, user, OrganizationCreate(name=DEMO_ORG_NAME)
            )
            logger.info("Demo: created the workspace")

        brand = await session.scalar(
            select(Brand).where(
                Brand.organization_id == organization.id,
                Brand.name == DEMO_BRAND_NAME,
                Brand.deleted_at.is_(None),
            )
        )
        if brand is None:
            brand = await brand_service.create_brand(
                session, user, BrandCreate(organization_id=organization.id, **BRAND)
            )
            logger.info("Demo: created the brand")

        existing = set(
            await session.scalars(
                select(BrandDocument.original_filename).where(
                    BrandDocument.brand_id == brand.id,
                    BrandDocument.status != DocumentStatus.DELETED,
                )
            )
        )
        for filename, document_type in DOCUMENTS.items():
            path = SAMPLES_DIR / filename
            if filename in existing or not path.exists():
                continue
            upload = UploadFile(io.BytesIO(path.read_bytes()), filename=filename)
            document = await document_service.upload_document(
                session,
                brand=brand,
                user=user,
                upload=upload,
                document_type=document_type,
                storage=get_storage(),
                settings=settings,
            )
            dispatch.enqueue_ingestion(document.id)
            logger.info("Demo: uploaded %s", filename)

        campaign = await session.scalar(
            select(Campaign).where(
                Campaign.brand_id == brand.id, Campaign.name == DEMO_CAMPAIGN_NAME
            )
        )
        if campaign is None:
            campaign = await campaign_service.create_campaign(
                session,
                user,
                brand,
                CampaignCreate(brand_id=brand.id, name=DEMO_CAMPAIGN_NAME, brief=BRIEF),
            )
        user_id, brand_id, campaign_id = user.id, brand.id, campaign.id

    # The agents read the knowledge base, so wait until indexing has finished.
    await _wait_for_documents(sessions, brand_id)
    await _ensure_finished_run(sessions, user_id, campaign_id)


DOCUMENTS_WAIT_SECONDS = 600
RUN_WAIT_SECONDS = 1800


async def _wait_for_documents(sessions: async_sessionmaker, brand_id) -> None:
    for _ in range(DOCUMENTS_WAIT_SECONDS // POLL_SECONDS):
        async with sessions() as session:
            statuses = set(
                await session.scalars(
                    select(BrandDocument.status).where(
                        BrandDocument.brand_id == brand_id,
                        BrandDocument.status != DocumentStatus.DELETED,
                    )
                )
            )
        if not statuses & {DocumentStatus.PENDING, DocumentStatus.PROCESSING}:
            return
        await asyncio.sleep(POLL_SECONDS)
    logger.warning("Demo: documents still indexing after %ss; continuing", DOCUMENTS_WAIT_SECONDS)


async def _ensure_finished_run(sessions: async_sessionmaker, user_id, campaign_id) -> None:
    """Drive runs until one is approved by the Critic, approving concepts automatically.

    The showcase should be a PASSING campaign. A "needs review" run already makes the
    demo usable (see demo_ready), but while fewer than MAX_DEMO_RUN_ATTEMPTS runs exist,
    a new version is generated in the hope of a pass; the older ones stay visible.
    """
    from app.services import campaign_service
    from app.worker import dispatch

    for _ in range(MAX_DEMO_RUN_ATTEMPTS + 1):
        async with sessions() as session:
            runs = list(
                await session.scalars(
                    select(CampaignRun)
                    .where(CampaignRun.campaign_id == campaign_id)
                    .order_by(CampaignRun.version.desc())
                )
            )
            if any(r.status is RunStatus.COMPLETED for r in runs):
                logger.info("Demo: ready")
                return
            active = runs[0] if runs and not runs[0].status.is_terminal else None
            if active is None and len(runs) >= MAX_DEMO_RUN_ATTEMPTS:
                reviewable = any(r.status is RunStatus.NEEDS_REVIEW for r in runs)
                best = "needs review" if reviewable else "none finished"
                logger.warning("Demo: stopping after %d runs (best: %s)", len(runs), best)
                return
            if active is not None:  # e.g. interrupted by a restart: keep watching it
                run_id = active.id
            else:
                user = await session.get(User, user_id)
                campaign = await session.get(Campaign, campaign_id)
                run = await campaign_service.create_run(session, campaign, user)
                dispatch.enqueue_campaign_run(run.id)
                logger.info("Demo: started campaign run v%d", run.version)
                run_id = run.id

        status = await _autopilot(sessions, user_id, run_id)
        if status is RunStatus.COMPLETED:
            logger.info("Demo: ready")
            return


async def _autopilot(sessions: async_sessionmaker, user_id, run_id):
    """Watch a run; approve the first concept when the workflow asks for a decision."""
    from app.services import campaign_service
    from app.worker import dispatch

    for _ in range(RUN_WAIT_SECONDS // POLL_SECONDS):
        async with sessions() as session:
            run = await session.get(CampaignRun, run_id)
            if run.status.is_terminal:
                return run.status
            if run.status is RunStatus.AWAITING_APPROVAL:
                approval = await campaign_service.pending_approval(session, run_id)
                concepts = (approval.payload or {}).get("concepts", []) if approval else []
                if concepts:
                    user = await session.get(User, user_id)
                    await campaign_service.decide(
                        session,
                        approval,
                        user,
                        approve=True,
                        concept_id=concepts[0]["concept_id"],
                        feedback=None,
                    )
                    dispatch.enqueue_campaign_run(run_id)
                    logger.info("Demo: approved concept %s", concepts[0]["concept_id"])
        await asyncio.sleep(POLL_SECONDS)
    return None
