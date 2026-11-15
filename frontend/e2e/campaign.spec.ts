import path from "node:path"

import { expect, test, type Page } from "@playwright/test"

/**
 * Full product flow with the REAL agents (Gemini, RAG, Tavily) - takes a few minutes and
 * spends a few LLM / web-search credits. Run explicitly: npx playwright test campaign
 */
test.setTimeout(15 * 60_000)

const CORPUS = path.resolve(__dirname, "../../backend/evals/retrieval/corpus")

async function snap(page: Page, name: string, outputDir: string) {
  const dir = process.env.E2E_SCREENSHOTS ?? outputDir
  await page.screenshot({ path: path.join(dir, `${name}.png`), fullPage: true })
}

test("brief → live agents → approve concept → evaluation → edit script → PDF", async ({ page }, testInfo) => {
  const out = testInfo.outputDir

  // --- account, workspace, brand -------------------------------------------------------
  await page.goto("/register")
  await page.getByLabel("Full name").fill("Meera Planner")
  await page.getByLabel("Work email").fill(`campaign-${Date.now()}@example.com`)
  await page.getByLabel("Password", { exact: true }).fill("campaign-password-1")
  await page.getByLabel("Confirm password").fill("campaign-password-1")
  await page.getByRole("button", { name: "Create account" }).click()
  await page.getByLabel("Workspace name").fill("Campaign Studio")
  await page.getByRole("button", { name: "Create workspace" }).click()
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible()

  await page.getByRole("link", { name: "Brands" }).first().click()
  await page.getByRole("button", { name: "New brand" }).first().click()
  await page.getByLabel("Brand name").fill("MANO")
  await page.getByLabel("Industry").fill("Low-sugar sparkling beverages")
  await page.getByRole("button", { name: "Create brand" }).click()
  await page.getByLabel("Brand voice").fill("Witty, youthful, confident; never sarcastic")
  await page.getByRole("button", { name: "Add restriction" }).click()
  await page.getByLabel("Add restriction 1").fill("Never say 'healthy' or 'boosts immunity'")
  await page.getByRole("button", { name: "Save profile" }).click()
  await expect(page.getByText("Brand profile saved")).toBeVisible()

  await page.getByRole("tab", { name: "Knowledge base" }).click()
  await page
    .locator('input[type="file"]')
    .setInputFiles(["brand_guidelines.txt", "legal_compliance.txt", "product_catalogue.txt"].map((f) => path.join(CORPUS, f)))
  await expect(page.getByText("Indexed")).toHaveCount(3, { timeout: 90_000 })

  // --- campaign wizard -----------------------------------------------------------------
  await page.getByRole("link", { name: "Campaigns" }).first().click()
  await page.getByRole("link", { name: "New campaign" }).first().click()
  // Next 16 keeps previously visited routes mounted but hidden (<Activity>), so labels
  // like "Brand name" from the Brands page are still in the DOM: match exactly.
  await page.getByLabel("Brand", { exact: true }).click()
  await page.getByRole("option", { name: "MANO" }).click()
  await page.getByLabel("Campaign name").fill("Campus Launch")
  await page.getByLabel("Campaign objective").fill("Brand awareness")
  await page.getByRole("button", { name: "Continue" }).click()
  await page.getByLabel("Target audience").fill("College students aged 18-25 in Indian cities")
  await page.getByLabel("Tone (optional)").fill("Youthful, energetic and humorous")
  await page.getByRole("button", { name: "Continue" }).click()
  await page.getByLabel("Additional requirements (optional)").fill("Feature real student moments; end on the tagline.")
  await page.getByRole("button", { name: "Continue" }).click()
  await expect(page.getByText("College students aged 18-25 in Indian cities")).toBeVisible()
  await snap(page, "c01-wizard-review", out)
  await page.getByRole("button", { name: "Create & generate" }).click()

  // --- live run ------------------------------------------------------------------------
  await expect(page.getByText("Agent progress")).toBeVisible()
  await expect(page.getByText("Live", { exact: true })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText("Campaign Manager", { exact: true })).toBeVisible({ timeout: 120_000 })
  await snap(page, "c02-live-progress", out)

  await expect(page.getByText("Choose a concept")).toBeVisible({ timeout: 6 * 60_000 })
  await snap(page, "c03-concept-approval", out)
  await page.getByRole("button", { name: /^Approve C\d/ }).click()
  await expect(page.getByText(/approved — the Scriptwriter is starting/)).toBeVisible()

  // Production + critique; ends approved or flagged for review.
  await expect(page.getByRole("heading", { level: 1 }).locator("..").getByText(/^(Completed|Needs Review)$/)).toBeVisible({
    timeout: 8 * 60_000,
  })

  // --- evaluation dashboard -----------------------------------------------------------
  await page.getByRole("tab", { name: "Evaluation" }).click()
  await expect(page.getByText("Overall quality")).toBeVisible()
  await expect(page.getByRole("list", { name: "Dimension" })).toBeVisible()
  await snap(page, "c04-evaluation", out)
  await page.getByRole("button", { name: "View as table" }).first().click()
  await expect(page.getByRole("cell", { name: "Compliance" })).toBeVisible()

  // --- script editor: save a human edit as version 2 ----------------------------------
  await page.getByRole("tab", { name: "Script" }).click()
  await page.getByRole("button", { name: "Edit", exact: true }).click()
  await page.getByLabel("Scene 1 voiceover").fill("Exam week. Page four. Again.")
  await page.getByRole("button", { name: "Save as new version" }).click()
  await expect(page.getByText(/Saved as version 2/)).toBeVisible()
  await expect(page.getByText("Exam week. Page four. Again.")).toBeVisible()
  await snap(page, "c05-script-v2", out)

  await page.getByRole("tab", { name: "Storyboard" }).click()
  await expect(page.getByText("Image prompt").first()).toBeVisible()
  await snap(page, "c06-storyboard", out)

  // --- PDF export ---------------------------------------------------------------------
  const download = page.waitForEvent("download")
  await page.getByRole("button", { name: "Download PDF" }).click()
  expect((await download).suggestedFilename()).toMatch(/^campus-launch-v1\.pdf$/)
})
