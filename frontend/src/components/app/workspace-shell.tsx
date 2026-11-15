"use client"

import {
  BriefcaseIcon,
  Building2Icon,
  CheckIcon,
  ChevronsUpDownIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  MegaphoneIcon,
  SettingsIcon,
  ShieldAlertIcon,
} from "lucide-react"
import Link from "next/link"
import { useParams, usePathname, useRouter } from "next/navigation"
import { useEffect } from "react"

import { EmptyState } from "@/components/app/empty-state"
import { Logo } from "@/components/app/logo"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/lib/auth/auth-context"
import { initials, titleCase } from "@/lib/format"
import { cn } from "@/lib/utils"
import { rememberOrg } from "@/lib/workspace"

type NavItem = { href: string; label: string; icon: typeof LayoutDashboardIcon; soon?: boolean }

function navItems(orgId: string): NavItem[] {
  const base = `/orgs/${orgId}`
  return [
    { href: `${base}/dashboard`, label: "Dashboard", icon: LayoutDashboardIcon },
    { href: `${base}/brands`, label: "Brands", icon: BriefcaseIcon },
    { href: `${base}/campaigns`, label: "Campaigns", icon: MegaphoneIcon },
    { href: `${base}/settings`, label: "Settings", icon: SettingsIcon },
  ]
}

function NavLinks({ orgId, className }: { orgId: string; className?: string }) {
  const pathname = usePathname()
  return (
    <nav className={className}>
      {navItems(orgId).map(({ href, label, icon: Icon, soon }) => {
        const active = pathname.startsWith(href)
        if (soon) {
          return (
            <span
              key={href}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground/60"
              title="Campaign screens arrive in the next phase"
            >
              <Icon className="size-4" aria-hidden /> {label}
              <Badge variant="outline" className="ml-auto text-[10px]">
                Soon
              </Badge>
            </span>
          )
        }
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
              active
                ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
            )}
          >
            <Icon className={cn("size-4", active && "text-primary")} aria-hidden /> {label}
          </Link>
        )
      })}
    </nav>
  )
}

function OrgSwitcher({ orgId }: { orgId: string }) {
  const { user } = useAuth()
  const router = useRouter()
  const current = user?.organizations.find((o) => o.id === orgId)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-auto w-full justify-start gap-3 px-2 py-2">
          <span className="grid size-8 shrink-0 place-items-center rounded-md bg-muted">
            <Building2Icon className="size-4 text-muted-foreground" aria-hidden />
          </span>
          <span className="min-w-0 flex-1 text-left">
            <span className="block truncate text-sm font-medium">{current?.name}</span>
            <span className="block text-xs text-muted-foreground">
              {current ? titleCase(current.role) : ""}
            </span>
          </span>
          <ChevronsUpDownIcon className="size-4 text-muted-foreground" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
        {user?.organizations.map((org) => (
          <DropdownMenuItem key={org.id} onSelect={() => router.push(`/orgs/${org.id}/dashboard`)}>
            <span className="truncate">{org.name}</span>
            {org.id === orgId && <CheckIcon className="ml-auto size-4 text-primary" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => router.push("/orgs?choose")}>
          Manage workspaces…
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function UserMenu({ orgId }: { orgId: string }) {
  const { user, logout } = useAuth()
  const router = useRouter()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-auto w-full justify-start gap-3 px-2 py-2">
          <Avatar className="size-8">
            <AvatarFallback className="text-xs">{initials(user?.full_name)}</AvatarFallback>
          </Avatar>
          <span className="min-w-0 flex-1 text-left">
            <span className="block truncate text-sm">{user?.full_name}</span>
            <span className="block truncate text-xs text-muted-foreground">{user?.email}</span>
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuItem onSelect={() => router.push(`/orgs/${orgId}/settings`)}>
          <SettingsIcon /> Account settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => logout().then(() => router.replace("/login"))}>
          <LogOutIcon /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const { orgId } = useParams<{ orgId: string }>()
  const { user } = useAuth()
  const member = user?.organizations.some((o) => o.id === orgId)

  useEffect(() => {
    if (member) rememberOrg(orgId)
  }, [member, orgId])

  if (!member) {
    return (
      <main className="mx-auto max-w-lg px-4 py-24">
        <EmptyState
          icon={ShieldAlertIcon}
          title="Workspace not found"
          description="It doesn't exist or you are not a member of it."
          action={
            <Button asChild>
              <Link href="/orgs?choose">Your workspaces</Link>
            </Button>
          }
        />
      </main>
    )
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col gap-4 border-r border-sidebar-border bg-sidebar p-3 md:flex">
        <div className="px-2 pt-2 pb-1">
          <Logo />
        </div>
        <OrgSwitcher orgId={orgId} />
        <NavLinks orgId={orgId} className="flex flex-col gap-1" />
        <div className="mt-auto border-t border-sidebar-border pt-3">
          <UserMenu orgId={orgId} />
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        {/* compact navigation for small screens */}
        <div className="flex items-center gap-3 overflow-x-auto border-b border-border px-4 py-2 md:hidden">
          <Logo className="shrink-0 text-sm" />
          <NavLinks orgId={orgId} className="flex gap-1" />
        </div>
        <main className="mx-auto w-full max-w-6xl flex-1 space-y-8 px-4 py-8 sm:px-8">{children}</main>
      </div>
    </div>
  )
}
