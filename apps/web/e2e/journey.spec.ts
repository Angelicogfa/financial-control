import { expect, test } from "@playwright/test";
import path from "node:path";

import { FIXTURES, login, navigate } from "./helpers";

/** The whole cycle through the UI (item 14.2): strategy → import → follow → contribute →
 *  portfolio, home, performance and the global search → edit and delete a ledger entry. */
test("operational journey", async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());
  await login(page);

  // Strategy: a new version with different targets.
  await navigate(page, "Estratégia");
  await page.getByLabel("Meta de Ações", { exact: true }).fill("30");
  await page.getByLabel("Meta de Caixa", { exact: true }).fill("20");
  await page.getByRole("button", { name: "Salvar nova versão" }).click();
  await expect(page.getByText("Nova versão da estratégia salva.")).toBeVisible();

  // B3 statements: trades first, then movements (earnings and corporate events).
  await navigate(page, "Lançamentos");
  await page.getByRole("link", { name: "Importar extrato B3" }).click();
  await page.getByLabel("Arquivo (.xlsx ou .csv)", { exact: true }).setInputFiles(path.join(FIXTURES, "b3_negociacao.csv"));
  await expect(page.getByText("Ativos que ainda não estão cadastrados")).toBeVisible();
  await page.getByRole("button", { name: /^Importar \d+ linha/ }).click();
  await expect(page.getByText(/Importado: 6 operação/)).toBeVisible();
  await page.getByLabel("Arquivo (.xlsx ou .csv)", { exact: true }).setInputFiles(path.join(FIXTURES, "b3_movimentacao.csv"));
  await page.getByRole("button", { name: /^Importar \d+ linha/ }).click();
  // MXRF11 is unknown and pre-checked for registration, so its yield comes in too.
  await expect(page.getByText(/4 provento\(s\) e 2 evento\(s\); ativos cadastrados: MXRF11/)).toBeVisible();

  // Acompanhar: follow a ticker that is not in the catalog yet.
  await navigate(page, "Acompanhar");
  await page.getByLabel("Observar código", { exact: true }).fill("BBAS3");
  await page.getByLabel("Tipo", { exact: true }).fill("Ação B3");
  await page.getByRole("option", { name: "Ação B3", exact: true }).click();
  await page.getByRole("button", { name: "Adicionar" }).click();
  await expect(page.getByRole("link", { name: "BBAS3" })).toBeVisible();

  // A cash asset so the class below its band can receive the contribution.
  await navigate(page, "Carteira");
  await page.getByRole("link", { name: "Novo ativo" }).click();
  await page.getByLabel("Tipo", { exact: true }).fill("Caixa");
  await page.getByRole("option", { name: "Caixa", exact: true }).click();
  await page.getByLabel("Nome", { exact: true }).fill("Reserva corretora");
  await page.getByLabel("Preço manual", { exact: true }).fill("1");
  await page.getByRole("button", { name: "Cadastrar ativo" }).click();
  await expect(page.getByRole("navigation", { name: "Capítulos" })).toBeVisible();

  // Contribute and confirm.
  await navigate(page, "Aportar");
  await page.getByLabel("Quanto vai aportar (R$)", { exact: true }).fill("1000");
  await page.getByRole("button", { name: "Sugerir distribuição" }).click();
  await expect(page.getByRole("list", { name: "Peso de cada classe antes e depois do aporte" })).toBeVisible();
  await page.getByRole("button", { name: /^Confirmar [1-9]\d* compra/ }).click();
  await expect(page.getByText(/Plano confirmado/)).toBeVisible();

  // The results show up where they belong.
  await navigate(page, "Carteira");
  await expect(page.getByRole("link", { name: "ITSA4" })).toBeVisible();
  await expect(page.getByRole("link", { name: /^CAIXA-/ })).toBeVisible();
  await navigate(page, "Início");
  await expect(page.getByText("Como está a carteira")).toBeVisible();
  await expect(page.getByText("Patrimônio", { exact: true })).toBeVisible();
  await navigate(page, "Carteira");
  await page.getByRole("navigation", { name: "Seções de Carteira" }).getByRole("link", { name: "Rentabilidade" }).click();
  await expect(page.getByRole("heading", { name: "Desempenho" })).toBeVisible();

  // Global search: Ctrl+K finds the asset and opens its page by ticker.
  await page.keyboard.press("Control+k");
  await page.getByRole("combobox", { name: "Buscar ativo ou ação" }).fill("ITSA4");
  await page.getByRole("option", { name: /ITSA4/ }).first().click();
  await expect(page).toHaveURL(/\/ativo\/ITSA4$/);
  await expect(page.getByRole("navigation", { name: "Capítulos" })).toBeVisible();

  // Edit and delete ledger entries.
  await navigate(page, "Lançamentos");
  const contribution = page.getByRole("row").filter({ hasText: /Aporte #/ }).first();
  await contribution.getByRole("link", { name: "Editar" }).click();
  await page.getByLabel("Observação", { exact: true }).fill("Aporte revisado no E2E");
  await page.getByRole("button", { name: "Salvar" }).click();
  const revised = page.getByRole("row").filter({ hasText: "Aporte revisado no E2E" });
  await expect(revised).toBeVisible();
  await revised.getByRole("button", { name: "Excluir" }).click();
  await expect(revised).toHaveCount(0);
});
