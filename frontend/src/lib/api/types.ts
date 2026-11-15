/** Friendly aliases for generated API types (components["schemas"][...]). */
import type { components } from "./schema"

type S = components["schemas"]

export type User = S["MeResponse"]
export type OrganizationWithRole = S["OrganizationWithRole"]
export type Role = S["MembershipRole"]
export type Member = S["MemberRead"]
export type Brand = S["BrandRead"]
export type BrandSummary = S["BrandSummary"]
export type BrandCreate = S["BrandCreate"]
export type BrandUpdate = S["BrandUpdate"]
export type BrandDocument = S["DocumentRead"]
export type DocumentStatus = S["DocumentStatus"]
export type DocumentType = S["DocumentType"]
export type Dashboard = S["Dashboard"]

// Campaigns
export type RunStatus = S["RunStatus"]
export type Campaign = S["CampaignRead"]
export type CampaignRead = S["CampaignRead"]
export type CampaignCreate = S["CampaignCreate"]
export type BriefFields = S["BriefFields"]
export type RunSummary = S["RunSummary"]
export type RunDetail = S["RunDetail"]
export type AgentStep = S["AgentRunRead"]
export type Approval = S["ApprovalRead"]
export type OutputType = S["OutputType"]
export type Output = S["OutputRead"]
export type EvaluationSummary = S["EvaluationSummary"]
export type Script = S["Script"]
export type Storyboard = S["Storyboard"]

// Shapes of output `content` that never appear in an endpoint signature (stored as JSON).
// They mirror backend/app/agents/schemas.py.
export type Concept = {
  concept_id: string
  title: string
  core_idea: string
  creative_angle: string
  target_emotion: string
  opening_hook: string
  storytelling_approach: string
  key_message: string
  unique_selling_proposition: string
  call_to_action: string
  reasoning: string
}
export type ConceptSet = {
  concepts: Concept[]
  recommended_concept_id: string
  recommendation_reasoning: string
  campaign_messaging: string
}
export type Severity = "critical" | "high" | "medium" | "low"
export type Issue = {
  dimension: string
  severity: Severity
  target: "script" | "storyboard"
  description: string
  suggestion: string
}
export type BrandResearch = {
  summary: string
  products: string
  target_audience: string
  brand_personality: string
  tone_of_voice: string
  positioning: string
  key_messages: string[]
  prohibited_claims: string[]
  visual_guidelines: string
  past_campaign_learnings: string[]
  knowledge_gaps: string[]
  cited_sources: number[]
}
export type BrandSource = {
  source: number
  document_id: string
  original_filename: string
  source_page: number | null
  chunk_index: number
  excerpt: string
  cited: boolean
}
export type CompetitorReport = S["CompetitorReport"]
export const TERMINAL_STATUSES: RunStatus[] = ["completed", "needs_review", "concepts_rejected", "failed"]
export const ACTIVE_STATUSES: RunStatus[] = ["queued", "running"]
