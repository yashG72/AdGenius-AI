/**
 * Server-Sent Events over fetch (not EventSource).
 *
 * The browser's EventSource cannot send an Authorization header, so we read the
 * text/event-stream body ourselves. The stream reconnects automatically with
 * Last-Event-ID, so no agent step is missed after a network blip, a server restart or
 * the backend's max-stream timeout.
 */

import { getAccessToken, refreshAccessToken } from "@/lib/auth/token-store"
import { API_URL } from "@/lib/config"

export type SseMessage = { event: string; id?: string; data: unknown }

type Options = {
  signal: AbortSignal
  onMessage: (message: SseMessage) => void
  /** Stop reconnecting after this event (e.g. "end"). */
  finalEvent?: string
}

function parseBlock(block: string): SseMessage | null {
  let event = "message"
  let id: string | undefined
  const data: string[] = []
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue // comment / keep-alive
    const colon = line.indexOf(":")
    const field = colon === -1 ? line : line.slice(0, colon)
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "")
    if (field === "event") event = value
    else if (field === "id") id = value
    else if (field === "data") data.push(value)
  }
  if (!data.length) return null
  try {
    return { event, id, data: JSON.parse(data.join("\n")) }
  } catch {
    return { event, id, data: data.join("\n") }
  }
}

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener("abort", () => {
      clearTimeout(timer)
      resolve()
    })
  })

export async function streamEvents(path: string, { signal, onMessage, finalEvent }: Options): Promise<void> {
  let lastEventId: string | undefined
  let delay = 1000
  let refreshed = false

  while (!signal.aborted) {
    try {
      const token = await getAccessToken()
      const response = await fetch(`${API_URL}${path}`, {
        signal,
        headers: {
          Accept: "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
        },
      })
      if (response.status === 401 && !refreshed) {
        refreshed = true
        if (await refreshAccessToken()) continue
      }
      if (!response.ok || !response.body) {
        if (response.status >= 400 && response.status < 500) return // not allowed / not found
        throw new Error(`stream failed: ${response.status}`)
      }
      refreshed = false
      delay = 1000

      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
      let buffer = ""
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += value.replace(/\r\n/g, "\n")
        let boundary: number
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const message = parseBlock(buffer.slice(0, boundary))
          buffer = buffer.slice(boundary + 2)
          if (!message) continue
          if (message.id) lastEventId = message.id
          onMessage(message)
          if (finalEvent && message.event === finalEvent) return
        }
      }
    } catch (error) {
      if (signal.aborted) return
      console.warn("event stream interrupted, reconnecting", error)
    }
    await sleep(delay, signal) // server closed the stream or the network dropped
    delay = Math.min(delay * 2, 15_000)
  }
}
