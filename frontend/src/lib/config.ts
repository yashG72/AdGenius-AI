/** Public backend URL (the browser calls the FastAPI API directly for data). */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

/** Same backend, as seen from the Next.js server (route handlers). */
export const SERVER_API_URL = process.env.API_URL ?? API_URL
