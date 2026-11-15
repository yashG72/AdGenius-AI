"use client"

import { useParams } from "next/navigation"

import { PageHeader } from "@/components/app/page-header"
import { AccountSettings } from "@/components/settings/account-settings"
import { MembersSettings } from "@/components/settings/members-settings"
import { WorkspaceSettings } from "@/components/settings/workspace-settings"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useMembership } from "@/lib/queries/organizations"

export default function SettingsPage() {
  const { orgId } = useParams<{ orgId: string }>()
  const org = useMembership(orgId)
  if (!org) return null // the workspace shell already handles non-members

  return (
    <>
      <PageHeader title="Settings" description="Your account, this workspace and who has access to it." />
      <Tabs defaultValue="account">
        <TabsList>
          <TabsTrigger value="account">Account</TabsTrigger>
          <TabsTrigger value="workspace">Workspace</TabsTrigger>
          <TabsTrigger value="members">Members</TabsTrigger>
        </TabsList>
        <TabsContent value="account" className="mt-6">
          <AccountSettings />
        </TabsContent>
        <TabsContent value="workspace" className="mt-6">
          <WorkspaceSettings org={org} />
        </TabsContent>
        <TabsContent value="members" className="mt-6">
          <MembersSettings org={org} />
        </TabsContent>
      </Tabs>
    </>
  )
}
