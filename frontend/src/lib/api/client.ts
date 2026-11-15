/**
 * Typed API client.
 *
 * `paths` is generated from the backend's OpenAPI schema (npm run gen:api), so every
 * URL, parameter, body and response below is type-checked against the real API.
 *
 * Middleware:
 * - attaches `Authorization: Bearer <access token>` (refreshing it first if needed);
 * - on a 401, refreshes the token ONCE and replays the original request.
 */

import createClient, { type Middleware } from "openapi-fetch"

import { getAccessToken, refreshAccessToken } from "@/lib/auth/token-store"
import { API_URL } from "@/lib/config"

import { ApiError } from "./errors"
import type { paths } from "./schema"

// Copies of outgoing requests (bodies can only be read once), for the 401 replay.
const pending = new Map<string, Request>()

const auth: Middleware = {
  async onRequest({ request, id }) {
    const token = await getAccessToken()
    if (token) request.headers.set("Authorization", `Bearer ${token}`)
    pending.set(id, request.clone())
    return request
  },
  async onResponse({ response, id }) {
    const original = pending.get(id)
    pending.delete(id)
    if (response.status !== 401 || !original) return response
    const token = await refreshAccessToken()
    if (!token) return response // session really expired: caller sees the 401
    const retry = new Request(original)
    retry.headers.set("Authorization", `Bearer ${token}`)
    return fetch(retry)
  },
  onError({ id }) {
    pending.delete(id)
  },
}

export const api = createClient<paths>({ baseUrl: API_URL })
api.use(auth)

/** For unauthenticated endpoints (e.g. registration): no token handling at all. */
export const publicApi = createClient<paths>({ baseUrl: API_URL })

/** Return `data` or throw an ApiError built from the backend's error envelope. */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise
  if (error !== undefined || !response.ok) throw ApiError.from(response.status, error)
  return data as T
}
