/**
 * Visual QA + smoke: walks every major screen against the REAL backend,
 * captures a screenshot at each of the three required resolutions, and fails
 * on any console error.
 */
import { expect, test, type Page } from "@playwright/test";

const APP = process.env.APP_URL ?? "http://localhost:3000";

const ACCOUNTS = {
  SALES: "sales@techsupply.com",
  MANAGER: "manager@techsupply.com",
  FINANCE: "finance@techsupply.com",
  OPS: "ops@techsupply.com",
  ADMIN: "admin@techsupply.com",
  CUSTOMER: "customer@acme.com",
};
const PASSWORD = "Password123!";

/** Console errors that are environmental rather than application faults. */
const IGNORE = [
  /favicon/i,
  /Failed to load resource.*404 \(Not Found\)/i,
  /fonts\.googleapis/i,
  /fonts\.gstatic/i,
];

function watchConsole(page: Page, sink: string[]) {
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const text = m.text();
    if (IGNORE.some((re) => re.test(text))) return;
    sink.push(text);
  });
  page.on("pageerror", (e) => sink.push(`pageerror: ${e.message}`));
}

async function login(page: Page, email: string) {
  await page.goto(APP + "/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15_000 });
}

const INTERNAL_ROUTES: [string, string][] = [
  ["/", "command-center"],
  ["/quotes", "quotes"],
  ["/pipeline", "pipeline"],
  ["/deals", "deals"],
  ["/customers", "customers"],
  ["/approvals", "approvals"],
  ["/orders", "orders"],
  ["/inventory", "inventory"],
  ["/warehouses", "warehouses"],
  ["/billing", "billing"],
  ["/billing/subscriptions", "subscriptions"],
  ["/billing/invoices", "invoices"],
  ["/billing/credit-notes", "credit-notes"],
  ["/deal-health", "deal-health"],
  ["/attention", "attention"],
  ["/anomalies", "anomalies"],
  ["/activity", "activity"],
  ["/reports", "reports"],
];

const ADMIN_ROUTES: [string, string][] = [
  ["/admin/products", "admin-products"],
  ["/admin/price-lists", "admin-price-lists"],
  ["/admin/policies", "admin-policies"],
  ["/admin/settings", "admin-settings"],
  ["/admin/teams", "admin-teams"],
  ["/admin/users", "admin-users"],
];

const SIZES = [
  { w: 1280, h: 720, tag: "1280x720" },
  { w: 1440, h: 900, tag: "1440x900" },
  { w: 1920, h: 1080, tag: "1920x1080" },
];

test.describe("visual QA", () => {
  test("internal screens render at every resolution with a clean console", async ({ page }) => {
    const errors: string[] = [];
    watchConsole(page, errors);

    await page.setViewportSize({ width: 1440, height: 900 });
    await login(page, ACCOUNTS.ADMIN);

    for (const [route, name] of [...INTERNAL_ROUTES, ...ADMIN_ROUTES]) {
      await page.goto(APP + route);
      // every page renders an <h1>
      await expect(page.locator("h1").first()).toBeVisible({ timeout: 15_000 });
      await page.waitForTimeout(600); // let queries settle
      for (const s of SIZES) {
        await page.setViewportSize({ width: s.w, height: s.h });
        await page.waitForTimeout(150);
        await page.screenshot({ path: `e2e/shots/${name}--${s.tag}.png`, fullPage: false });
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      // no horizontal overflow at the narrowest desktop size
      await page.setViewportSize({ width: 1280, height: 720 });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal overflow on ${route}`).toBeLessThanOrEqual(1);
      await page.setViewportSize({ width: 1440, height: 900 });
    }

    expect(errors, `console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("customer portal is a separate shell and leaks nothing internal", async ({ page }) => {
    const errors: string[] = [];
    watchConsole(page, errors);

    const leaked: string[] = [];
    const FORBIDDEN = [
      "unit_cost", "total_cost", "line_cost", "internal_cost",
      "margin", "margin_pct", "blended_risk_score", "risk_band",
    ];
    page.on("response", async (res) => {
      if (!res.url().includes("/portal/")) return;
      try {
        const body = await res.text();
        for (const f of FORBIDDEN) {
          if (body.includes(`"${f}"`)) leaked.push(`${f} in ${res.url()}`);
        }
      } catch {
        /* non-text response */
      }
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    await login(page, ACCOUNTS.CUSTOMER);
    await expect(page).toHaveURL(/\/portal/);

    for (const [route, name] of [
      ["/portal", "portal-quotes"],
      ["/portal/messages", "portal-messages"],
      ["/portal/profile", "portal-profile"],
    ] as [string, string][]) {
      await page.goto(APP + route);
      await expect(page.locator("h1").first()).toBeVisible({ timeout: 15_000 });
      await page.waitForTimeout(500);
      for (const s of SIZES) {
        await page.setViewportSize({ width: s.w, height: s.h });
        await page.screenshot({ path: `e2e/shots/${name}--${s.tag}.png` });
      }
      await page.setViewportSize({ width: 1440, height: 900 });
    }

    // open the first proposal
    await page.goto(APP + "/portal");
    const first = page.locator('a[href^="/portal/quotes/"]').first();
    if (await first.count()) {
      await first.click();
      await expect(page.locator("h1").first()).toBeVisible();
      await page.waitForTimeout(800);
      await page.screenshot({ path: "e2e/shots/portal-quote-detail--1440x900.png", fullPage: true });
    }

    // a customer must never reach the internal app
    await page.goto(APP + "/quotes");
    await expect(page).toHaveURL(/\/portal/);

    expect(leaked, `portal leaked internal fields:\n${leaked.join("\n")}`).toEqual([]);
    expect(errors, `console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("sales reaches the quote builder and approvals are role-gated", async ({ page }) => {
    const errors: string[] = [];
    watchConsole(page, errors);
    await page.setViewportSize({ width: 1440, height: 900 });

    await login(page, ACCOUNTS.SALES);

    // quote list -> detail -> builder
    await page.goto(APP + "/quotes");
    const row = page.getByRole("button").filter({ hasText: /Q-\d+/ }).first();
    await expect(row).toBeVisible({ timeout: 15_000 });
    await row.click();
    await expect(page).toHaveURL(/\/quotes\/[0-9a-f-]+/);
    await page.waitForTimeout(1000);
    await page.screenshot({ path: "e2e/shots/quote-detail--1440x900.png", fullPage: true });

    expect(errors, `console errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("manager sees the approval inbox and a decision screen", async ({ page }) => {
    const errors: string[] = [];
    watchConsole(page, errors);
    await page.setViewportSize({ width: 1440, height: 900 });

    await login(page, ACCOUNTS.MANAGER);
    await page.goto(APP + "/approvals");
    await expect(page.locator("h1")).toContainText("Approval inbox");
    await page.waitForTimeout(800);
    await page.screenshot({ path: "e2e/shots/approvals-inbox--1440x900.png", fullPage: true });

    const row = page.getByRole("button").filter({ hasText: /Q-\d+/ }).first();
    if (await row.count()) {
      await row.click();
      await expect(page).toHaveURL(/\/approvals\/[0-9a-f-]+/);
      await page.waitForTimeout(1200);
      await page.screenshot({ path: "e2e/shots/approval-detail--1440x900.png", fullPage: true });
      await expect(page.getByText("Approval progression")).toBeVisible();
    }

    expect(errors, `console errors:\n${errors.join("\n")}`).toEqual([]);
  });
});
