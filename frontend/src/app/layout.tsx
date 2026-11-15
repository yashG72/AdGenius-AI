import type { Metadata } from "next"
import { Geist, Geist_Mono } from "next/font/google"

import { Providers } from "./providers"
import "./globals.css"

const sans = Geist({ variable: "--font-sans", subsets: ["latin"] })
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] })

export const metadata: Metadata = {
  title: { default: "AdGenius AI", template: "%s · AdGenius AI" },
  description: "A multi-agent creative agency: research, strategy, scripts and storyboards.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // Dark-only product: the `dark` class activates the charcoal theme tokens.
    <html lang="en" className={`dark ${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
