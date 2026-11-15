"use client"

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"

import { api, publicApi, unwrap } from "@/lib/api/client"
import { ApiError } from "@/lib/api/errors"
import type { User } from "@/lib/api/types"
import {
  SESSION_EXPIRED_EVENT,
  clearAccessToken,
  refreshAccessToken,
  setAccessToken,
} from "@/lib/auth/token-store"

type Status = "loading" | "authenticated" | "anonymous"

type RegisterInput = { email: string; password: string; full_name: string }

type AuthContextValue = {
  status: Status
  user: User | undefined
  login: (email: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export const meQueryKey = ["me"] as const

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<Status>("loading")

  // On load, try to restore the session from the httpOnly refresh cookie.
  useEffect(() => {
    refreshAccessToken().then((token) => setStatus(token ? "authenticated" : "anonymous"))
    const expired = () => {
      queryClient.clear()
      setStatus("anonymous")
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, expired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expired)
  }, [queryClient])

  const me = useQuery({
    queryKey: meQueryKey,
    queryFn: () => unwrap(api.GET("/api/v1/auth/me")),
    enabled: status === "authenticated",
  })

  const login = useCallback(async (email: string, password: string) => {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
    const body = await response.json()
    if (!response.ok) throw ApiError.from(response.status, body)
    setAccessToken(body)
    setStatus("authenticated")
  }, [])

  const register = useCallback(
    async (input: RegisterInput) => {
      await unwrap(publicApi.POST("/api/v1/auth/register", { body: input }))
      await login(input.email, input.password)
    },
    [login],
  )

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined)
    clearAccessToken()
    queryClient.clear()
    setStatus("anonymous")
  }, [queryClient])

  const value = useMemo(
    () => ({ status, user: me.data, login, register, logout }),
    [status, me.data, login, register, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>")
  return context
}
