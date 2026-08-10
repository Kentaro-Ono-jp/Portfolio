import { writeFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

import { canonicalInvoicePdf } from "../e2e/pdf-fixture";

const username = process.env.PORTFOLIO_AWS_SMOKE_USERNAME;
const password = process.env.PORTFOLIO_AWS_SMOKE_PASSWORD;
const output = process.env.PORTFOLIO_AWS_SMOKE_OUTPUT;
const resource = process.env.PORTFOLIO_AWS_SMOKE_RESOURCE;

if (
  username === undefined ||
  password === undefined ||
  output === undefined ||
  resource === undefined
) {
  throw new Error(
    "AWS smoke requires private runtime identity inputs and an output path.",
  );
}

test("proves the managed authenticated asynchronous lifecycle", async ({
  page,
}) => {
  let pkceObserved = false;
  let resourceBindingObserved = false;
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      url.pathname.endsWith("/oauth2/authorize") &&
      url.searchParams.get("code_challenge_method") === "S256" &&
      (url.searchParams.get("code_challenge")?.length ?? 0) >= 43
    ) {
      pkceObserved = true;
    }
    if (
      url.pathname.endsWith("/oauth2/authorize") &&
      url.searchParams.get("resource") === resource
    ) {
      resourceBindingObserved = true;
    }
  });

  await page.goto("/");
  expect(new URL(page.url()).protocol).toBe("https:");
  await expect(
    page.getByRole("heading", {
      name: "From source PDF to a traceable ML result.",
      exact: true,
    }),
  ).toBeVisible();

  await page
    .getByRole("link", {
      name: "Sign in as synthetic reviewer",
      exact: true,
    })
    .click();
  const usernameInput = page.locator(
    'input[name="username"], input[name="login"]',
  );
  await usernameInput.first().fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page
    .locator('button[type="submit"], input[type="submit"]')
    .first()
    .click();
  await expect(
    page.getByText("Synthetic reviewer signed in", { exact: true }),
  ).toBeVisible();

  const session = await page.request.get("/api/auth/session");
  expect(session.status()).toBe(200);
  const sessionBody = (await session.json()) as Record<string, unknown>;
  expect(sessionBody.authenticated).toBe(true);
  expect("accessToken" in sessionBody).toBe(false);

  await page.getByLabel("Source PDF", { exact: true }).setInputFiles({
    name: "canonical-invoice.pdf",
    mimeType: "application/pdf",
    buffer: canonicalInvoicePdf(),
  });
  await page
    .getByRole("button", { name: "Start classification", exact: true })
    .click();
  await expect(
    page.getByLabel("Machine result", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Measured lineage", { exact: true }),
  ).toBeVisible();

  const sourceLink = page.getByRole("link", {
    name: "View private source PDF",
    exact: true,
  });
  const sourceHref = await sourceLink.getAttribute("href");
  expect(sourceHref).not.toBeNull();
  const source = await page.request.get(sourceHref!);
  expect(source.status()).toBe(200);
  expect(source.headers()["content-type"]).toContain("application/pdf");
  expect((await source.body()).subarray(0, 5).toString("ascii")).toBe("%PDF-");

  const approve = page.getByRole("button", {
    name: /^Approve (invoice|report) classification$/u,
  });
  await approve.click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await expect(
    page.getByText("review.approved", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("document.submitted", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("processing.completed", { exact: true }),
  ).toBeVisible();

  writeFileSync(
    output,
    `${JSON.stringify(
      {
        accessTokenSession: true,
        asynchronousCompletion: true,
        auditHistory: true,
        authorizationCodePkce: pkceObserved,
        externalHttps: true,
        reviewDecision: true,
        resourceBoundAudience: resourceBindingObserved,
        sourcePrivate: true,
        upload: true,
      },
      null,
      2,
    )}\n`,
    "utf8",
  );
});
