import { Logo } from "@/components/app/logo"
import { ServerWakeNotice } from "@/components/app/server-wake-notice"

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <main className="relative grid min-h-screen place-items-center overflow-hidden px-4 py-12">
      {/* subtle warm glow behind the card */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 left-1/2 size-[36rem] -translate-x-1/2 rounded-full bg-primary/10 blur-3xl"
      />
      <div className="relative w-full max-w-sm space-y-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <Logo className="text-lg" />
          <p className="text-sm text-muted-foreground">
            Your multi-agent creative agency — from brief to storyboard.
          </p>
        </div>
        <ServerWakeNotice />
        {children}
      </div>
    </main>
  )
}
