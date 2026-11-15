/** Mirrors the backend's error envelope: {"error": {code, message, details, request_id}}. */
export type ErrorBody = {
  error?: { code?: string; message?: string; details?: unknown; request_id?: string | null }
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: unknown,
    readonly requestId?: string | null,
  ) {
    super(message)
    this.name = "ApiError"
  }

  static from(status: number, body: unknown): ApiError {
    const error = (body as ErrorBody | undefined)?.error
    return new ApiError(
      status,
      error?.code ?? "http_error",
      error?.message ?? `Request failed (${status})`,
      error?.details,
      error?.request_id,
    )
  }

  /** First validation message, e.g. "brief.duration_seconds: must be <= 180". */
  get displayMessage(): string {
    if (this.code === "validation_error" && Array.isArray(this.details) && this.details.length) {
      const first = this.details[0] as { loc?: unknown[]; msg?: string }
      const field = (first.loc ?? []).filter((p) => p !== "body").join(".")
      return field ? `${field}: ${first.msg}` : (first.msg ?? this.message)
    }
    return this.message
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.displayMessage
  if (error instanceof Error) return error.message
  return "Something went wrong."
}
