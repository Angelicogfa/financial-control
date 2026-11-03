import { expect, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const FIXTURES = path.resolve(HERE, "../../api/tests/fixtures");

export async function login(page: Page): Promise<void> {
  const username = process.env.E2E_USERNAME ?? "e2e";
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error("E2E_PASSWORD is not set (scripts/e2e.sh sets it)");
  await page.goto("/inicio");
  await page.getByLabel("Usuário", { exact: true }).fill(username);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("complementary", { name: "Menu principal" })).toBeVisible();
}

/** Clicks the menu item whose label is exactly `item`; a count badge may follow it
 *  ("Início 3 alertas"), but "Carteira" never matches "Saúde da carteira". */
export async function navigate(page: Page, item: string): Promise<void> {
  const escaped = item.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const name = new RegExp(`^${escaped}(\\s|$)`);
  await page.getByRole("complementary", { name: "Menu principal" }).getByRole("link", { name }).click();
}
