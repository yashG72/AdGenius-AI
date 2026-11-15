import path from "node:path"

import { expect, test, type Page } from "@playwright/test"

// Screenshots go to E2E_SCREENSHOTS (or Playwright's per-test output folder).
async function snap(page: Page, name: string, outputDir: string) {
  const dir = process.env.E2E_SCREENSHOTS ?? outputDir
  await page.screenshot({ path: path.join(dir, `${name}.png`), fullPage: true })
}

const GUIDELINES = path.resolve(__dirname, "../../backend/evals/retrieval/corpus/brand_guidelines.txt")

test("register → workspace → brand profile → knowledge base → dashboard → sign out", async ({
  page,
}, testInfo) => {
  const email = `e2e-${Date.now()}@example.com`
  const out = testInfo.outputDir

  // 1. Route guard: protected pages send signed-out visitors to /login?next=...
  await page.goto("/orgs")
  await expect(page).toHaveURL(/\/login\?next=%2Forgs/)
  await snap(page, "01-login", out)

  // 2. Register (auto-signs in) and land on the workspace picker.
  await page.getByRole("link", { name: "Create an account" }).click()
  await page.getByLabel("Full name").fill("Asha Tester")
  await page.getByLabel("Work email").fill(email)
  await page.getByLabel("Password", { exact: true }).fill("e2e-password-123")
  await page.getByLabel("Confirm password").fill("e2e-password-123")
  await page.getByRole("button", { name: "Create account" }).click()
  await expect(page.getByRole("heading", { name: /Welcome, Asha/ })).toBeVisible()

  // 3. Create a workspace -> dashboard.
  await page.getByLabel("Workspace name").fill("E2E Creative")
  await page.getByRole("button", { name: "Create workspace" }).click()
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible()
  await expect(page.getByText("No campaigns yet")).toBeVisible()
  await snap(page, "02-dashboard-empty", out)

  // 4. Create a brand from the Brands page.
  await page.getByRole("link", { name: "Brands" }).first().click()
  await page.getByRole("button", { name: "New brand" }).first().click()
  await page.getByLabel("Brand name").fill("MANO")
  await page.getByLabel("Industry").fill("Beverages")
  await page.getByRole("button", { name: "Create brand" }).click()
  await expect(page.getByRole("heading", { name: "MANO" })).toBeVisible()

  // 5. Edit the profile: voice, a restriction and a colour; save.
  await page.getByLabel("Brand voice").fill("Witty, youthful, never sarcastic")
  await page.getByRole("button", { name: "Add restriction" }).click()
  await page.getByLabel("Add restriction 1").fill("Never say 'healthy'")
  await page.getByRole("button", { name: "Add colour" }).click()
  await page.getByLabel("Colour name").fill("Mango Gold")
  await page.getByLabel("Hex").fill("#FFB300")
  await page.getByRole("button", { name: "Save profile" }).click()
  await expect(page.getByText("Brand profile saved")).toBeVisible()
  await snap(page, "03-brand-profile", out)

  // 6. Reload: the session is restored from the httpOnly cookie and data persisted.
  await page.reload()
  await expect(page.getByLabel("Brand voice")).toHaveValue("Witty, youthful, never sarcastic")
  await expect(page.getByLabel("Add restriction 1")).toHaveValue("Never say 'healthy'")

  // 7. Knowledge base: upload a document and wait for the worker to index it.
  await page.getByRole("tab", { name: "Knowledge base" }).click()
  await page.locator('input[type="file"]').setInputFiles(GUIDELINES)
  await expect(page.getByText("brand_guidelines.txt").first()).toBeVisible()
  await expect(page.getByText("Indexed")).toBeVisible({ timeout: 60_000 })
  await snap(page, "04-knowledge-base", out)

  // 8. Dashboard reflects the new brand and document.
  await page.getByRole("link", { name: "Dashboard" }).first().click()
  await expect(page.getByText("1 document uploaded")).toBeVisible()
  await expect(page.getByRole("link", { name: "brand_guidelines.txt" })).toBeVisible()
  await snap(page, "05-dashboard", out)

  // 9. Settings → members lists you as owner.
  await page.getByRole("link", { name: "Settings" }).first().click()
  await page.getByRole("tab", { name: "Members" }).click()
  await expect(page.getByText("(you)")).toBeVisible()
  await snap(page, "06-settings-members", out)

  // 10. Sign out: the session is revoked and protected pages require login again.
  await page.getByRole("button", { name: /Asha Tester/ }).click()
  await page.getByRole("menuitem", { name: "Sign out" }).click()
  await expect(page).toHaveURL(/\/login/)
  await page.goto("/orgs")
  await expect(page).toHaveURL(/\/login/)
})
