"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { UserPlusIcon } from "lucide-react"
import { useRouter } from "next/navigation"
import { Controller, useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { ConfirmDialog } from "@/components/app/confirm-dialog"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldError, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { errorMessage } from "@/lib/api/errors"
import type { Member, OrganizationWithRole, Role } from "@/lib/api/types"
import { useAuth } from "@/lib/auth/auth-context"
import { formatRelative, initials, titleCase } from "@/lib/format"
import { canManage, useMemberMutations, useMembers } from "@/lib/queries/organizations"

const ROLES: Role[] = ["owner", "admin", "member"]

const addSchema = z.object({
  email: z.email("Enter a valid email"),
  role: z.enum(["owner", "admin", "member"]),
})

/** Mirrors the backend rules so the UI never offers an action that would be refused. */
function rolesYouCanAssign(yourRole: Role): Role[] {
  return yourRole === "owner" ? ROLES : ["admin", "member"]
}

export function MembersSettings({ org }: { org: OrganizationWithRole }) {
  const { user } = useAuth()
  const router = useRouter()
  const { data: members, isPending } = useMembers(org.id)
  const { add, changeRole, remove } = useMemberMutations(org.id)
  const manager = canManage(org.role)
  const assignable = rolesYouCanAssign(org.role)

  const form = useForm({
    resolver: zodResolver(addSchema),
    defaultValues: { email: "", role: "member" as Role },
  })

  const onAdd = form.handleSubmit(async (values) => {
    try {
      await add.mutateAsync({ email: values.email.toLowerCase(), role: values.role })
      toast.success(`${values.email} added`)
      form.reset()
    } catch (e) {
      toast.error(errorMessage(e))
    }
  })

  const canEdit = (m: Member) => manager && (org.role === "owner" || m.role !== "owner")
  // The last owner can't leave (the backend would refuse), so don't offer it.
  const owners = members?.filter((m) => m.role === "owner").length ?? 0
  const canLeave = (m: Member) => !(m.role === "owner" && owners <= 1)

  return (
    <div className="space-y-6">
      {manager && (
        <Card>
          <CardHeader>
            <CardTitle>Add a member</CardTitle>
            <CardDescription>They need an AdGenius account first (email invitations come later).</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onAdd} noValidate className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <Field className="flex-1" data-invalid={!!form.formState.errors.email}>
                <FieldLabel htmlFor="member-email">Email</FieldLabel>
                <Input id="member-email" type="email" placeholder="teammate@agency.com" {...form.register("email")} />
                <FieldError errors={[form.formState.errors.email]} />
              </Field>
              <Field className="sm:w-40">
                <FieldLabel htmlFor="member-role">Role</FieldLabel>
                <Controller
                  control={form.control}
                  name="role"
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger id="member-role">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {assignable.map((r) => (
                          <SelectItem key={r} value={r}>
                            {titleCase(r)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </Field>
              <Button type="submit" disabled={add.isPending}>
                <UserPlusIcon /> Add
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Members</CardTitle>
          <CardDescription>Owners manage everything; admins manage brands and members; members create work.</CardDescription>
        </CardHeader>
        <CardContent>
          {isPending ? (
            <Skeleton className="h-32" />
          ) : (
            <ul className="divide-y divide-border">
              {members?.map((m) => {
                const isYou = m.user_id === user?.id
                return (
                  <li key={m.user_id} className="flex flex-wrap items-center gap-3 py-3">
                    <Avatar className="size-9">
                      <AvatarFallback className="text-xs">{initials(m.full_name)}</AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">
                        {m.full_name} {isYou && <span className="text-muted-foreground">(you)</span>}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {m.email} · joined {formatRelative(m.joined_at)}
                      </p>
                    </div>
                    {canEdit(m) && !isYou ? (
                      <Select
                        value={m.role}
                        onValueChange={(role) =>
                          changeRole.mutate(
                            { userId: m.user_id, role: role as Role },
                            {
                              onSuccess: () => toast.success(`${m.full_name} is now ${role}`),
                              onError: (e) => toast.error(errorMessage(e)),
                            },
                          )
                        }
                      >
                        <SelectTrigger className="w-32" aria-label={`Role of ${m.full_name}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {assignable.map((r) => (
                            <SelectItem key={r} value={r}>
                              {titleCase(r)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <Badge variant="secondary">{titleCase(m.role)}</Badge>
                    )}
                    {((isYou && canLeave(m)) || (!isYou && canEdit(m))) && (
                      <ConfirmDialog
                        title={isYou ? "Leave this workspace?" : `Remove ${m.full_name}?`}
                        description={
                          isYou
                            ? "You will lose access to its brands and campaigns."
                            : "They will lose access to this workspace immediately."
                        }
                        confirmLabel={isYou ? "Leave" : "Remove"}
                        onConfirm={() =>
                          remove.mutate(m.user_id, {
                            onSuccess: () => {
                              toast.success(isYou ? "You left the workspace" : `${m.full_name} removed`)
                              if (isYou) router.replace("/orgs?choose")
                            },
                            onError: (e) => toast.error(errorMessage(e)),
                          })
                        }
                        trigger={
                          <Button variant="ghost" size="sm">
                            {isYou ? "Leave" : "Remove"}
                          </Button>
                        }
                      />
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
