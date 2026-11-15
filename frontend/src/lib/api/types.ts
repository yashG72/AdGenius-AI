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
export type RunStatus = S["RunStatus"]
export type CampaignRead = S["CampaignRead"]
