import { expect, test, type Page } from "@playwright/test";

import path from "node:path";

import { FIXTURES, login, navigate } from "./helpers";
import { ROUTES } from "./routes";

/** Smoke of every screen (Phase 48.R0): it opens with a title, is not the "page not
 *  found" screen and throws no uncaught error. Runs after the journey (scripts/e2e.sh), so the
 *  portfolio has assets and the asset page can be opened from it. */

async function expectScreen(page: Page, errors: string[], where: string): Promise<void> {
  await expect(page.getByRole("heading", { level: 1 }).first(), where).toBeVisible();
  await expect(page.getByText("Página não encontrada"), where).toHaveCount(0);
  expect(errors, `${where}: uncaught errors`).toEqual([]);
}

test("every address opens its screen (Phase 48.R3)", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);

  for (const route of ROUTES) {
    await page.goto(route.path);
    await expect(page, route.path).toHaveURL(new RegExp(`${route.path}$`));
    await expectScreen(page, errors, `${route.screen} (${route.path})`);
  }
});

test("the root opens Início and an old address is gone (Phase 48.R9)", async ({ page }) => {
  await login(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/inicio$/);
  await page.goto("/portfolio");
  await expect(page.getByText("Página não encontrada").first()).toBeVisible();
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

test("Acompanhar keeps an alert rule and the asset keeps its thesis (Phase 48.R6)", async ({ page }) => {
  await login(page);
  await page.goto("/acompanhar?tab=alerts");
  const form = page.getByRole("form", { name: "Nova regra de alerta" });
  await form.getByLabel("Código", { exact: true }).fill("ITSA4");
  await form.getByLabel("Limite", { exact: true }).fill("1000");
  await form.getByRole("button", { name: "Criar regra" }).click();
  await expect(page.getByRole("table", { name: "Regras de alerta" })).toContainText("Preço de ITSA4 abaixo de R$ 1.000,00");

  await page.goto("/ativo/ITSA4?capitulo=tese");
  const thesis = page.getByRole("region", { name: "Minha tese" });
  await thesis.getByLabel("Nota da tese", { exact: true }).fill("Holding com desconto; revisar no próximo balanço");
  await thesis.getByRole("button", { name: "Guardar nota" }).click();
  await expect(thesis.getByRole("list", { name: "Notas da tese" })).toContainText("Holding com desconto");

  await page.goto("/acompanhar?tab=theses");
  await expect(page.getByRole("list", { name: "Teses" })).toContainText("ITSA4");
});

test("the monthly income tax opens from the Carteira (Phase 48.R7)", async ({ page }) => {
  await login(page);
  await navigate(page, "Carteira");
  await page.getByRole("navigation", { name: "Seções de Carteira" }).getByRole("link", { name: "Imposto" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Imposto" })).toBeVisible();
  await expect(page.getByLabel("Imposto do ano")).toBeVisible();
});

test("a goal shows its progress and suggests the amount in Aportar (Phase 48.R8)", async ({ page }) => {
  await login(page);
  await navigate(page, "Planejar");
  await page.getByRole("navigation", { name: "Seções de Planejar" }).getByRole("link", { name: "Metas" }).click();
  const form = page.getByRole("form", { name: "Nova meta" });
  await form.getByLabel("Nome", { exact: true }).fill("Primeiro milhão");
  await form.getByLabel("Patrimônio (R$)", { exact: true }).fill("1000000");
  await form.getByLabel("Até", { exact: true }).fill("2040-01-01");
  await form.getByLabel("Aporte mensal (R$)", { exact: true }).fill("100");
  await form.getByRole("button", { name: "Criar meta" }).click();
  const goal = page.getByRole("list", { name: "Metas" }).getByRole("listitem").filter({ hasText: "Primeiro milhão" });
  await expect(goal).toContainText("Fora do caminho");
  await expect(goal.getByRole("progressbar")).toBeVisible();

  await navigate(page, "Aportar");
  await expect(page.getByRole("note", { name: "Pelas suas metas" })).toContainText("Primeiro milhão");
});

test("an unknown address shows the not-found screen", async ({ page }) => {
  await login(page);
  await page.goto("/does-not-exist");
  await expect(page.getByText("Página não encontrada").first()).toBeVisible();
});
