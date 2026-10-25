import { expect, test } from "@playwright/test";

import { login, navigate } from "./helpers";

/** Runs after `docker compose restart` (scripts/e2e.sh): nothing of the journey was lost. */
test("data survives a restart of the containers", async ({ page }) => {
  await login(page);
  await navigate(page, "Carteira");
  for (const ticker of ["ITSA4", "WEGE3", "HGLG11"]) {
    await expect(page.getByRole("link", { name: ticker })).toBeVisible();
  }
  await navigate(page, "Lançamentos");
  await expect(page.getByRole("row").filter({ hasText: "Importado da B3" }).first()).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "Aporte revisado no E2E" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Eventos corporativos" }).click();
  await expect(page.getByRole("row").filter({ hasText: "Desdobramento" })).toBeVisible();
  await navigate(page, "Estratégia");
  await expect(page.getByLabel("Meta de Ações")).toHaveValue("30");
  await navigate(page, "Pesquisar");
  await page.getByRole("tab", { name: "Em observação" }).click();
  await expect(page.getByRole("link", { name: "BBAS3" })).toBeVisible();
});
