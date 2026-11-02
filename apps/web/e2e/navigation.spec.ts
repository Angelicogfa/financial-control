import { expect, test, type Page } from "@playwright/test";

import path from "node:path";

import { FIXTURES, login, navigate } from "./helpers";
import { CURRENT_ROUTES, NEW_ROUTES } from "./routes";

/** Smoke of every current screen (Phase 48.R0): it opens with a title, is not the "page not
 *  found" screen and throws no uncaught error. Runs after the journey (scripts/e2e.sh), so the
 *  portfolio has assets and the asset page can be opened from it. */

async function expectScreen(page: Page, errors: string[], where: string): Promise<void> {
  await expect(page.getByRole("heading", { level: 1 }).first(), where).toBeVisible();
  await expect(page.getByText("Página não encontrada"), where).toHaveCount(0);
  expect(errors, `${where}: uncaught errors`).toEqual([]);
}

test("every current screen opens", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);

  for (const route of CURRENT_ROUTES) {
    await page.goto(route.path);
    await expectScreen(page, errors, `${route.screen} (${route.path})`);
  }
});

test("every new address opens its screen (Phase 48.R3)", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);

  for (const route of NEW_ROUTES) {
    await page.goto(route.path);
    await expect(page, route.path).toHaveURL(new RegExp(`${route.path}$`));
    await expectScreen(page, errors, `${route.screen} (${route.path})`);
  }
});

test("an old address lands on its new place, filters included", async ({ page }) => {
  await login(page);
  await page.goto("/tools/compare?tickers=ITSA4,WEGE3");
  await expect(page).toHaveURL(/\/explorar\/comparar\?tickers=ITSA4%2CWEGE3$/);
  await page.goto("/research?tab=watchlist");
  await expect(page).toHaveURL(/\/acompanhar$/);
});

test("an asset opens from the portfolio, in chapters", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);

  await navigate(page, "Carteira");
  await page.getByRole("link", { name: "ITSA4" }).click();
  await expect(page).toHaveURL(/\/ativo\/ITSA4$/);
  await expectScreen(page, errors, "ativo ITSA4");
  await expect(page.getByRole("navigation", { name: "Capítulos" })).toBeVisible();
});

test("the portfolio links the asset by ticker and a chapter opens its details (Phase 48.R4)", async ({ page }) => {
  await login(page);
  await navigate(page, "Carteira");
  const href = await page.getByRole("link", { name: "ITSA4" }).getAttribute("href");
  expect(href).toBe("/ativo/ITSA4");
  await page.goto("/ativo/ITSA4");
  await page.getByRole("button", { name: "Ver detalhes: Está barato?" }).click();
  await expect(page.getByRole("button", { name: "Ocultar detalhes: Está barato?" })).toBeVisible();
});

test("the position check compares the B3 statement and saves it (Phase 48.R5)", async ({ page }) => {
  await login(page);
  await navigate(page, "Carteira");
  await page.getByRole("navigation", { name: "Seções de Carteira" }).getByRole("link", { name: "Conferir" }).click();
  await page
    .getByLabel("Extrato de Posição (.xlsx ou .csv)", { exact: true })
    .setInputFiles(path.join(FIXTURES, "b3_posicao-2026-10-31.csv"));
  await page.getByRole("button", { name: "Conferir", exact: true }).click();
  const table = page.getByRole("table", { name: "Linhas da conferência" });
  await expect(table.getByRole("row").filter({ hasText: "ZZZZ3" })).toContainText("Só na B3");
  await expect(table.getByRole("row").filter({ hasText: "ITSA4" })).toContainText("Só no livro");
  await page.getByRole("button", { name: "Gravar conferência" }).click();
  await expect(page.getByRole("heading", { name: "Conferência de 31/10/2026" })).toBeVisible();
  await expect(page.getByText(/diferença\(s\) em aberto/)).toBeVisible();
});

test("an unknown address shows the not-found screen", async ({ page }) => {
  await login(page);
  await page.goto("/does-not-exist");
  await expect(page.getByText("Página não encontrada").first()).toBeVisible();
});
