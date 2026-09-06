/**
 * Demo access verification.
 *
 * Proves three things: every seeded account signs in and lands in the right
 * experience, the switcher re-authenticates rather than shortcutting, and the
 * feature adds no way around the backend's authorisation.
 */
import { expect, test, type Page } from "@playwright/test";

const APP = process.env.APP_URL ?? "http://localhost:3000";
const API = process.env.API_URL ?? "http://127.0.0.1:8010";

/** Must match scripts/seed.py SEED_USERS exactly. */
const ACCOUNTS = [
  { role: "SALES", email: "sales@techsupply.com", name: "Sam Rivera", title: "Sales", landing: "/", internal: true },
  { role: "MANAGER", email: "manager@techsupply.com", name: "Morgan Chen", title: "Sales Manager", landing: "/approvals", internal: true },
  { role: "FINANCE", email: "finance@techsupply.com", name: "Fran Delgado", title: "Finance", landing: "/approvals", internal: true },
  { role: "OPS", email: "ops@techsupply.com", name: "Omar Petrov", title: "Operations", landing: "/orders", internal: true },
  { role: "ADMIN", email: "admin@techsupply.com", name: "Avery Stone", title: "Administrator", landing: "/", internal: true },
  { role: "CUSTOMER", email: "customer@acme.com", name: "Casey Nolan", title: "Customer", landing: "/portal", internal: false },
] as const;

async function openPicker(page: Page) {
  await page.goto(APP + "/login");
  await page.getByRole("button", { name: /Demo accounts/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

async function enterAs(page: Page, title: string, email: string) {
  await openPicker(page);
  await page.getByRole("button", { name: new RegExp(`Enter as ${title} — ${email}`) }).click();
  // Selecting a role boots the app fresh at the role's landing route, so wait
  // for the document to settle before touching the page.
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 25_000 });
  await page.waitForLoadState("domcontentloaded");
  await expect(page.locator("nav").first()).toBeVisible({ timeout: 25_000 });
}

test.describe.configure({ mode: "serial" });

test("the picker lists exactly the six seeded accounts", async ({ page }) => {
  await openPicker(page);
  const dialog = page.getByRole("dialog");
  for (const a of ACCOUNTS) {
    await expect(dialog.getByText(a.email, { exact: true })).toBeVisible();
    await expect(dialog.getByText(a.name, { exact: false }).first()).toBeVisible();
  }
  // no invented accounts
  await expect(dialog.getByRole("button", { name: /^Enter as/ })).toHaveCount(ACCOUNTS.length);
  await page.screenshot({ path: "e2e/shots/demo-accounts-dialog.png" });
});

for (const a of ACCOUNTS) {
  test(`${a.role}: signs in through the real flow, lands correctly, and logs out`, async ({ page }) => {
    // capture the login request to prove the normal endpoint is used
    const loginCalls: { url: string; body: string }[] = [];
    page.on("request", (r) => {
      if (r.url().endsWith("/auth/login") && r.method() === "POST") {
        loginCalls.push({ url: r.url(), body: r.postData() ?? "" });
      }
    });

    await enterAs(page, a.title, a.email);

    // a real POST /auth/login carrying this account's credentials
    expect(loginCalls.length).toBe(1);
    expect(loginCalls[0].url).toContain(`${API}/auth/login`);
    expect(loginCalls[0].body).toContain(a.email);

    // landed in the right experience
    if (a.internal) {
      expect(page.url()).toContain(a.landing);
      await expect(page.getByText(a.role, { exact: true }).first()).toBeVisible();
      await expect(page.getByText(a.name).first()).toBeVisible();
      // internal chrome present, portal chrome absent
      await expect(page.getByRole("navigation", { name: "Modules" })).toBeVisible();
    } else {
      await expect(page).toHaveURL(/\/portal/);
      await expect(page.getByRole("navigation", { name: "Portal sections" })).toBeVisible();
      await expect(page.getByRole("navigation", { name: "Modules" })).toHaveCount(0);
    }

    // the session is a genuine backend session: /users/me agrees on the role
    const me = await page.evaluate(async (api) => {
      const t = sessionStorage.getItem("df360.access");
      const r = await fetch(`${api}/users/me`, { headers: { Authorization: `Bearer ${t}` } });
      return r.json();
    }, API);
    expect(me.email).toBe(a.email);
    expect(me.role).toBe(a.role);
    expect(me.is_internal).toBe(a.internal);

    // logout clears the session and returns to the login screen
    await page.getByRole("button", { name: /Sign out|Avery|Sam|Morgan|Fran|Omar/ }).first().click();
    const signOut = page.getByRole("menuitem", { name: "Sign out" });
    if (await signOut.count()) await signOut.click();
    await page.waitForURL(/\/login/, { timeout: 15_000 });
    expect(await page.evaluate(() => sessionStorage.getItem("df360.access"))).toBeNull();
  });
}

test("the in-app switcher re-authenticates and moves between shells", async ({ page }) => {
  test.setTimeout(180_000);

  /** Whoever the backend says we are, read from a live token. */
  const whoami = () =>
    page.evaluate(async (api) => {
      const t = sessionStorage.getItem("df360.access");
      const r = await fetch(`${api}/users/me`, { headers: { Authorization: `Bearer ${t}` } });
      return r.json();
    }, API);

  // the presenter's path: sales -> manager -> finance -> customer -> ops
  await enterAs(page, "Sales", "sales@techsupply.com");
  await expect(page.getByRole("navigation", { name: "Modules" })).toBeVisible();
  expect((await whoami()).role).toBe("SALES");

  const hop = async (title: string, expect_: { role: string; url: RegExp; portal?: boolean }) => {
    await page.getByRole("button", { name: "Switch demo role" }).click();
    await page.getByRole("menuitem", { name: new RegExp(title) }).click();

    // Two roles can share a landing route, so waiting on the URL alone can
    // resolve before the switch happens. Wait for the server-side identity.
    await expect
      .poll(async () => (await whoami().catch(() => ({ role: null }))).role, { timeout: 25_000 })
      .toBe(expect_.role);

    await page.waitForURL(expect_.url, { timeout: 25_000 });
    await expect(
      page.getByRole("navigation", { name: expect_.portal ? "Portal sections" : "Modules" }),
    ).toBeVisible();
    expect((await whoami()).is_internal).toBe(!expect_.portal);
  };

  await hop("Sales Manager", { role: "MANAGER", url: /\/approvals/ });
  await hop("Finance", { role: "FINANCE", url: /\/approvals/ });
  await hop("Customer", { role: "CUSTOMER", url: /\/portal/, portal: true });
  // and back into the internal app
  await hop("Operations", { role: "OPS", url: /\/orders/ });

  await page.screenshot({ path: "e2e/shots/demo-switcher.png" });
});

test("demo access opens no hole in authentication or authorisation", async ({ page }) => {
  await page.goto(APP + "/login");

  // 1. an unauthenticated visitor cannot reach the app by URL
  await page.goto(APP + "/quotes");
  await expect(page).toHaveURL(/\/login/);

  // 2. the client mints nothing — no session exists until the server responds
  expect(await page.evaluate(() => sessionStorage.getItem("df360.access"))).toBeNull();

  // 3. a wrong password fails, so the picker is not a side door
  const bad = await page.evaluate(async (api) => {
    const r = await fetch(`${api}/auth/login`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "admin@techsupply.com", password: "not-the-password" }),
    });
    return r.status;
  }, API);
  expect(bad).toBe(401);

  // 4. the customer's real token is refused by an internal endpoint —
  //    the backend, not the UI, is what stops them
  await enterAs(page, "Customer", "customer@acme.com");
  await expect(page.getByRole("navigation", { name: "Portal sections" })).toBeVisible();
  const forbidden = await page.evaluate(async (api) => {
    const t = sessionStorage.getItem("df360.access");
    const r = await fetch(`${api}/quotes?limit=1`, { headers: { Authorization: `Bearer ${t}` } });
    return { status: r.status, body: await r.json() };
  }, API);
  expect(forbidden.status).toBe(403);
  expect(forbidden.body.error.code).toBe("PORTAL_USER_FORBIDDEN");

  // 5. and a sales token cannot read the approval inbox
  await page.getByRole("button", { name: "Switch demo role" }).click();
  await page.getByRole("menuitem", { name: /Sales/ }).first().click();
  await expect(page.getByRole("navigation", { name: "Modules" })).toBeVisible({ timeout: 25_000 });
  const inbox = await page.evaluate(async (api) => {
    const t = sessionStorage.getItem("df360.access");
    const r = await fetch(`${api}/approvals/inbox`, { headers: { Authorization: `Bearer ${t}` } });
    return r.status;
  }, API);
  expect(inbox).toBe(403);
});
