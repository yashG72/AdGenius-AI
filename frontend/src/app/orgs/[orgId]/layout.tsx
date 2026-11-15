import { WorkspaceShell } from "@/components/app/workspace-shell"

export default function WorkspaceLayout({ children }: LayoutProps<"/orgs/[orgId]">) {
  return <WorkspaceShell>{children}</WorkspaceShell>
}
