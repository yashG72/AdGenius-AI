"""Agent input/output contracts.

Every agent returns one of these validated Pydantic models (via structured LLM output),
never free text. That makes outputs storable, displayable and safe to route on.
Field descriptions double as instructions to the model.
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]

Platform = Literal[
    "instagram", "youtube", "tiktok", "facebook", "linkedin", "x", "tv", "web", "other"
]
VideoFormat = Literal["9:16", "16:9", "1:1", "4:5"]


# ---------- Campaign brief (user input) ----------


class CampaignBrief(BaseModel):
    brand_id: uuid.UUID
    campaign_name: ShortText
    objective: Text = Field(description="Campaign objective, e.g. brand awareness.")
    product_description: Text | None = None
    marketing_objective: Text | None = None
    target_audience: Text
    platform: Platform = "instagram"
    duration_seconds: int = Field(default=30, ge=5, le=180)
    language: ShortText = "English"
    tone: ShortText | None = None
    video_format: VideoFormat = "9:16"
    num_concepts: int = Field(default=3, ge=1, le=5)
    budget: ShortText | None = None
    additional_requirements: Text | None = None
    competitor_research: bool = True
    competitor_focus: ShortText | None = None

    @field_validator("campaign_name", "objective", "target_audience")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


# ---------- Campaign Manager ----------


class ExecutionPlan(BaseModel):
    campaign_summary: str = Field(description="One-paragraph restatement of what we must make.")
    key_constraints: list[str] = Field(
        default_factory=list, description="Hard requirements (duration, platform, format, ...)."
    )
    brand_research_questions: list[str] = Field(
        default_factory=list,
        description="3-8 questions to answer from the brand's own documents.",
    )
    competitor_research_focus: str = Field(
        default="", description="What competitor/market research should concentrate on."
    )
    success_criteria: list[str] = Field(default_factory=list)


# ---------- Brand Research Agent ----------


class BrandResearch(BaseModel):
    summary: str
    products: str = Field(default="", description="Products/specifications relevant to the brief.")
    target_audience: str = ""
    brand_personality: str = ""
    tone_of_voice: str = ""
    positioning: str = ""
    key_messages: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(
        default_factory=list, description="Claims/messaging the brand must never use."
    )
    visual_guidelines: str = ""
    past_campaign_learnings: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(
        default_factory=list, description="Important things the documents did not cover."
    )
    cited_sources: list[int] = Field(
        default_factory=list, description="Numbers of the document sources relied on."
    )


# ---------- Creative Strategist ----------


class Concept(BaseModel):
    concept_id: str = Field(description="Short id, e.g. C1.")
    title: str
    core_idea: str
    creative_angle: str
    target_emotion: str
    opening_hook: str = Field(description="What happens/is said in the first 2-3 seconds.")
    storytelling_approach: str
    key_message: str
    unique_selling_proposition: str
    call_to_action: str
    reasoning: str = Field(description="Why this works for this brand, audience and platform.")


class ConceptSet(BaseModel):
    concepts: list[Concept]
    recommended_concept_id: str
    recommendation_reasoning: str
    campaign_messaging: str = Field(description="Core campaign message shared by all concepts.")


# ---------- Scriptwriter ----------


class DialogueLine(BaseModel):
    speaker: str
    line: str


class ScriptScene(BaseModel):
    scene_number: int
    duration_seconds: float = Field(gt=0)
    start_time: float = 0
    end_time: float = 0
    visual_summary: str
    voiceover: str = ""
    dialogue: list[DialogueLine] = Field(default_factory=list)
    on_screen_text: str = ""
    sound: str = Field(default="", description="Music cue / sound effects for this scene.")


class Script(BaseModel):
    title: str
    duration_seconds: float = 0
    opening_hook: str
    scenes: list[ScriptScene] = Field(min_length=1)
    music_suggestion: str = ""
    call_to_action: str
    timing_adjusted: bool = False


# ---------- Visual Director ----------


class ImagePrompt(BaseModel):
    prompt: str = Field(description="Complete, self-contained text-to-image prompt.")
    visual_style: str
    subject: str
    environment: str
    lighting: str
    composition: str
    camera_perspective: str
    aspect_ratio: str = ""
    negative_prompt: str = Field(default="", description="What the image must NOT contain.")


class StoryboardScene(BaseModel):
    scene_number: int
    duration_seconds: float = Field(gt=0)
    start_time: float = 0
    end_time: float = 0
    scene_description: str
    visual_direction: str
    composition: str = ""
    camera_angle: str
    camera_movement: str
    lighting: str
    voiceover: str = ""
    dialogue: list[DialogueLine] = Field(default_factory=list)
    on_screen_text: str = ""
    transition: str = Field(description="Transition into the next scene.")
    image_prompt: ImagePrompt


class Storyboard(BaseModel):
    visual_style: str
    consistency_notes: str = Field(
        description="Recurring characters, palette, props and look kept identical across scenes."
    )
    scenes: list[StoryboardScene] = Field(min_length=1)
    total_duration_seconds: float = 0
    timing_adjusted: bool = False


# ---------- Critic ----------

DIMENSIONS = (
    "brand_consistency",
    "storytelling_quality",
    "hook_strength",
    "audience_relevance",
    "platform_suitability",
    "creative_originality",
    "script_quality",
    "visual_consistency",
    "factual_accuracy",
    "compliance",
)


class DimensionScores(BaseModel):
    brand_consistency: int = Field(ge=0, le=100)
    storytelling_quality: int = Field(ge=0, le=100)
    hook_strength: int = Field(ge=0, le=100)
    audience_relevance: int = Field(ge=0, le=100)
    platform_suitability: int = Field(ge=0, le=100)
    creative_originality: int = Field(ge=0, le=100)
    script_quality: int = Field(ge=0, le=100)
    visual_consistency: int = Field(ge=0, le=100)
    factual_accuracy: int = Field(ge=0, le=100)
    compliance: int = Field(ge=0, le=100, description="Compliance with brand restrictions.")


class Issue(BaseModel):
    dimension: str
    severity: Literal["low", "medium", "high", "critical"]
    target: Literal["script", "storyboard"] = Field(
        description="Which production output must change to fix it."
    )
    description: str
    suggestion: str


class CriticReview(BaseModel):
    scores: DimensionScores
    issues: list[Issue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    overall_feedback: str


class Evaluation(BaseModel):
    """Critic output plus deterministic checks and the computed verdict."""

    scores: DimensionScores
    overall_score: float
    issues: list[Issue]
    strengths: list[str]
    overall_feedback: str
    passed: bool
    threshold: float
    iteration: int
