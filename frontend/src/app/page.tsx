import { redirect } from "next/navigation"

// The workspace picker decides where to go (and sends signed-out users to /login).
export default function Home() {
  redirect("/orgs")
}
