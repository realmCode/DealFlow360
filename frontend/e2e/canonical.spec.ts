/**
 * The canonical DealFlow360 journey, driven entirely through the UI against
 * the real backend.
 *
 *   login -> build -> policy -> submit -> manager -> finance -> send
 *   -> customer counter -> material change -> stale approval
 *   -> confirmation blocked -> re-approval -> confirm -> order
 *   -> allocate -> fulfil -> billing -> audit -> deal health
 *
 * Every number asserted is read back from the screen, which means it came
 * from the API. Nothing is hardcoded in the client.
 */
import { expect, test, type Page } from "@playwright/test";

const APP = process.env.APP_URL ?? "http://localhost:3000";
const API = process.env.API_URL ?? "http://127.0.0.1:8010";
const PASSWORD = "Password123!";

test.describe.configure({ mode: "serial" });

async function login(page: Page, email: string) {
  await page.goto(APP + "/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20_000 });
}

async function logout(page: Page) {
  await page.evaluate(() => sessionStorage.clear());
}

const jr = async (r: Response) => {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
};

async function adminHeaders() {
  const auth = await jr(await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "admin@techsupply.com", password: PASSWORD }),
  }));
  return { "Content-Type": "application/json", Authorization: `Bearer ${auth.tokens.access_token}` };
}

/**
 * Restore the canonical stock levels.
 *
 * Repeated runs legitimately consume inventory, and an exhausted warehouse
 * makes the allocator backorder everything — correct behaviour, but it hides
 * the multi-warehouse split this journey is meant to demonstrate. Setting the
 * seed levels (60 Main / 40 East laptops) is test setup, not fabrication: the
 * split itself is still computed by the backend.
 */
async function restock() {
  const H = await adminHeaders();
  const warehouses = await jr(await fetch(`${API}/warehouses`, { headers: H }));
  const products = await jr(await fetch(`${API}/products?limit=50`, { headers: H }));
  const wh: Record<string, string> = {};
  for (const w of warehouses) wh[w.code] = w.id;
  const pr: Record<string, string> = {};
  for (const p of products.items ?? products) pr[p.sku] = p.id;

  const levels: [string, string, string][] = [
    ["MAIN", "HW-LAPTOP-01", "60"],
    ["EAST", "HW-LAPTOP-01", "40"],
    ["MAIN", "HW-MONITOR-27", "150"],
    ["EAST", "HW-MONITOR-27", "50"],
  ];
  for (const [code, sku, qty] of levels) {
    await jr(await fetch(`${API}/admin/inventory`, {
      method: "POST", headers: H,
      body: JSON.stringify({
        warehouse_id: wh[code], product_id: pr[sku],
        quantity_on_hand: qty, reorder_point: "10",
      }),
    }));
  }
}

/** Seed a fresh quote through the API so the UI walk starts from a known state. */
async function seedQuote() {
  const j = async (r: Response) => {
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  };
  const auth = await j(await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "sales@techsupply.com", password: PASSWORD }),
  }));
  const tok = auth.tokens.access_token;
  const H = { "Content-Type": "application/json", Authorization: `Bearer ${tok}` };

  const customers = await j(await fetch(`${API}/customers`, { headers: H }));
  const products = await j(await fetch(`${API}/products?limit=50`, { headers: H }));
  const bySku: Record<string, string> = {};
  for (const p of products.items ?? products) bySku[p.sku] = p.id;

  const tag = Date.now();
  const deal = await j(await fetch(`${API}/deals`, {
    method: "POST", headers: H,
    body: JSON.stringify({
      name: `UI journey ${tag}`, customer_profile_id: customers[0].id,
      stage: "PROPOSAL", expected_value: "0",
    }),
  }));
  const quote = await j(await fetch(`${API}/deals/${deal.id}/quotes`, {
    method: "POST", headers: H,
    body: JSON.stringify({
      title: `UI journey ${tag}`, order_discount_pct: "0",
      lines: [
        { product_id: bySku["HW-LAPTOP-01"], quantity: "100", discount_pct: "18" },
        { product_id: bySku["HW-MONITOR-27"], quantity: "100", discount_pct: "16" },
        { product_id: bySku["SV-INSTALL-01"], quantity: "1", discount_pct: "18" },
        { product_id: bySku["SB-SUPPORT-01"], quantity: "1", discount_pct: "0" },
      ],
    }),
  }));
  return { quoteId: quote.id as string, versionId: quote.current_version_id as string, number: quote.quote_number as string };
}

test("the canonical journey, end to end, through the UI", async ({ page }) => {
  test.setTimeout(240_000);
  await restock();
  const { quoteId, versionId, number } = await seedQuote();

  /* ---- 1. sales builds and submits -------------------------------------- */
  await login(page, "sales@techsupply.com");
  await page.goto(`${APP}/quotes/${quoteId}/versions/${versionId}/build`);

  // the engine's own numbers, read off the screen
  await expect(page.getByRole("heading", { name: "Commercial position" })).toBeVisible();
  const intel = page.locator("aside");
  await expect(intel.getByText("132,710.00").first()).toBeVisible({ timeout: 20_000 });
  await expect(intel.getByText("32,510.00").first()).toBeVisible();
  await expect(intel.getByText("24.50%").first()).toBeVisible();

  // blended risk, decomposed
  await expect(page.getByRole("heading", { name: "Blended risk" })).toBeVisible();
  await expect(intel.getByText("32.44").first()).toBeVisible();
  await expect(intel.getByText("Medium").first()).toBeVisible();

  // policy evaluation explains why
  await expect(page.getByText(/exceeds the Gold tier ceiling of 15%/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Approval this will need" })).toBeVisible();

  await page.screenshot({ path: "e2e/shots/journey-01-builder.png", fullPage: true });

  await page.getByRole("button", { name: "Submit for approval" }).click();
  await page.waitForURL(`**/quotes/${quoteId}`, { timeout: 20_000 });
  await expect(page.getByText("Pending approval").first()).toBeVisible();

  /* ---- 2. manager approves ---------------------------------------------- */
  await logout(page);
  await login(page, "manager@techsupply.com");
  await page.goto(APP + "/approvals");
  await page.getByRole("button").filter({ hasText: number }).first().click();
  await expect(page.getByRole("heading", { name: "Approval progression" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Why this quotation was flagged" })).toBeVisible();
  await page.screenshot({ path: "e2e/shots/journey-02-approval.png", fullPage: true });

  await page.getByRole("button", { name: "Approve", exact: true }).first().click();
  await page.getByLabel("Reason for your decision").fill("Strategic account; margin clears the floor.");
  await page.getByRole("button", { name: "Approve", exact: true }).last().click();
  await expect(page.getByText("Approved").first()).toBeVisible({ timeout: 20_000 });

  /* ---- 3. finance approves ---------------------------------------------- */
  await logout(page);
  await login(page, "finance@techsupply.com");
  await page.goto(APP + "/approvals");
  await page.getByRole("button").filter({ hasText: number }).first().click();
  await page.getByRole("button", { name: "Approve", exact: true }).first().click();
  await page.getByLabel("Reason for your decision").fill("Signing authority granted.");
  await page.getByRole("button", { name: "Approve", exact: true }).last().click();
  await page.waitForTimeout(1500);

  /* ---- 4. sales sends it ------------------------------------------------- */
  await logout(page);
  await login(page, "sales@techsupply.com");
  await page.goto(`${APP}/quotes/${quoteId}`);
  await page.getByRole("button", { name: "Send to customer" }).click();
  await expect(page.getByText("Sent to the customer portal").first()).toBeVisible({ timeout: 20_000 });

  /* ---- 5. the customer counters ----------------------------------------- */
  await logout(page);
  await login(page, "customer@acme.com");
  await page.goto(`${APP}/portal/quotes/${quoteId}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  // the portal must not show a cost, margin or risk figure anywhere
  const portalText = (await page.locator("body").innerText()).toLowerCase();
  expect(portalText).not.toContain("margin");
  expect(portalText).not.toContain("blended risk");
  expect(portalText).not.toContain("internal cost");
  await page.screenshot({ path: "e2e/shots/journey-03-portal.png", fullPage: true });

  await page.getByLabel(/Request/).first().fill("25");
  await page.getByRole("button", { name: /Submit request/ }).click();
  await expect(page.getByText(/being reviewed by the team|revised version/i).first())
    .toBeVisible({ timeout: 20_000 });

  /* ---- 6. confirmation is blocked --------------------------------------- */
  await page.goto(`${APP}/portal/quotes/${quoteId}`);
  await page.waitForTimeout(1200);
  const acceptBtn = page.getByRole("button", { name: "Accept proposal" });
  if (await acceptBtn.count()) await expect(acceptBtn).toBeDisabled();

  /* ---- 7. the internal side shows the stale approval --------------------- */
  await logout(page);
  await login(page, "sales@techsupply.com");
  await page.goto(`${APP}/quotes/${quoteId}`);
  await expect(page.getByText("This quotation changed after approval").first()).toBeVisible({ timeout: 20_000 });

  await page.getByRole("link", { name: /Review what changed/ }).click();
  await expect(page).toHaveURL(/\/impact$/);
  await expect(page.getByText(/previous approval is no longer valid/).first()).toBeVisible();
  await expect(page.getByText("Confirmation blocked").first()).toBeVisible();
  // v2 economics, straight from the engine
  await expect(page.getByText("124,310.00").first()).toBeVisible();
  await expect(page.getByText("19.3951%").first()).toBeVisible();
  await expect(page.getByText(/increased from 18% to 25%/).first()).toBeVisible();
  await page.screenshot({ path: "e2e/shots/journey-04-stale.png", fullPage: true });

  /* ---- 8. re-approval ---------------------------------------------------- */
  for (const who of ["manager@techsupply.com", "finance@techsupply.com"]) {
    await logout(page);
    await login(page, who);
    await page.goto(APP + "/approvals");
    const row = page.getByRole("button").filter({ hasText: number }).first();
    await expect(row).toBeVisible({ timeout: 20_000 });
    await row.click();
    await page.getByRole("button", { name: "Approve", exact: true }).first().click();
    await page.getByLabel("Reason for your decision").fill("Re-approved at the revised terms.");
    await page.getByRole("button", { name: "Approve", exact: true }).last().click();
    await page.waitForTimeout(1500);
  }

  /* ---- 9. send v2 and confirm -------------------------------------------- */
  await logout(page);
  await login(page, "sales@techsupply.com");
  await page.goto(`${APP}/quotes/${quoteId}`);
  const send = page.getByRole("button", { name: "Send to customer" });
  if (await send.count()) {
    await send.click();
    await page.waitForTimeout(1500);
  }

  await logout(page);
  await login(page, "customer@acme.com");
  await page.goto(`${APP}/portal/quotes/${quoteId}`);
  await page.getByRole("button", { name: "Accept proposal" }).click();
  await page.getByRole("button", { name: "Accept and create order" }).click();
  await expect(page.getByText("Order confirmed").first()).toBeVisible({ timeout: 25_000 });

  /* ---- 10. ops allocates and ships --------------------------------------- */
  await logout(page);
  await login(page, "ops@techsupply.com");
  await page.goto(APP + "/orders");
  await page.getByRole("button").filter({ hasText: /SO-\d+/ }).first().click();
  await expect(page).toHaveURL(/\/orders\/[0-9a-f-]+/);

  await page.getByRole("button", { name: "Allocate stock" }).click();
  await expect(page.getByRole("heading", { name: "Warehouse allocation" })).toBeVisible();
  await page.waitForTimeout(2500);
  // the split and its prose explanation both come from the backend
  await expect(page.getByText(/Sourced|backordered/).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Main Warehouse").first()).toBeVisible();
  await expect(page.getByText("East").first()).toBeVisible();
  await page.screenshot({ path: "e2e/shots/journey-05-fulfilment.png", fullPage: true });

  const ship = page.getByRole("button", { name: "Ship allocated stock" });
  if (await ship.count()) {
    await ship.click();
    await page.waitForTimeout(2000);
  }

  /* ---- 11. finance sees billing ------------------------------------------ */
  await logout(page);
  await login(page, "finance@techsupply.com");
  await page.goto(APP + "/billing");
  await expect(page.getByText("One-time").first()).toBeVisible();
  await expect(page.getByText("Recurring").first()).toBeVisible();
  await page.screenshot({ path: "e2e/shots/journey-06-billing.png", fullPage: true });

  /* ---- 12. audit trail and deal health ----------------------------------- */
  await page.goto(APP + "/activity");
  await expect(page.getByText(/Quote confirmed|Order created/i).first()).toBeVisible({ timeout: 20_000 });

  await page.goto(APP + "/deal-health");
  await expect(page.getByText("Average health").first()).toBeVisible();
  await page.screenshot({ path: "e2e/shots/journey-07-deal-health.png", fullPage: true });
});
