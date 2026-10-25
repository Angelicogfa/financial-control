import { expect, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const FIXTURES = path.resolve(HERE, "../../api/tests/fixtures");

export async function login(page: Page): Promise<void> {
  const username = process.env.E2E_USERNAME ?? "e2e";
  const password = process.env.E2E_PASSWORD;
  if (!password) throw new Error("E2E_PASSWORD is not set (scripts/e2e.sh sets it)");
  await page.goto("/home");
  await page.getByLabel("Usuário").fill(username);
  await page.getByLabel("Senha").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("complementary", { name: "Menu principal" })).toBeVisible();
}

export async function navigate(page: Page, item: string): Promise<void> {
  await page.getByRole("complementary", { name: "Menu principal" }).getByRole("link", { name: item }).click();
}
