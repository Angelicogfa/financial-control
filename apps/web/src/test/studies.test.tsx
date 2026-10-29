import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { StudyChapterDTO, StudyComparisonDTO, StudyDTO, StudySummaryDTO } from "../api/types";
import { LatestStudy } from "../pages/home/LatestStudy";
import { INITIAL_STUDY, reviewItems, toStudyRequest } from "../pages/simulation/NewStudyPage";
import { premisesLine } from "../pages/simulation/shared";
import { mockApi, type Call } from "./mockApi";
import { renderAt } from "./render";

const last = (calls: Call[], method: string, path: string) =>
  [...calls].reverse().find((c) => c.method === method && c.path === path);

function summary(overrides: Partial<StudySummaryDTO> = {}): StudySummaryDTO {
  return {
    id: 5,
    label: "Aposentadoria 2040",
    question: "COMPLETE",
    question_label: "Estudo completo",
    version: 2,
    created_at: "2026-11-05T10:00:00Z",
    status: "DONE",
    chapters_done: 3,
    chapters_total: 3,
    headline: "A chance de chegar a R$ 1,20 mi em 2040 é de 64%.",
    goal_probability: 0.64,
    goal_target: 1_200_000,
    goal_change: 0.03,
    ...overrides,
  };
}

function chapter(key: StudyChapterDTO["key"], overrides: Partial<StudyChapterDTO> = {}): StudyChapterDTO {
  const titles = { PAST: [1, "De onde viemos"], FUTURE: [2, "Para onde vamos"], IMPROVE: [3, "O que pode melhorar"] } as const;
  return {
    key,
    number: titles[key][0],
    title: titles[key][1],
    question: `Pergunta ${key}`,
    run_id: null,
    status: null,
    tone: "neutral",
    notes: [],
    ...overrides,
  };
}

function study(overrides: Partial<StudyDTO> = {}): StudyDTO {
  return {
    id: 5,
    label: "Aposentadoria 2040",
    question: "COMPLETE",
    question_label: "Estudo completo",
    premises: { monthly_contribution: 1500, horizon_years: 15, wealth_goal: 1_200_000, correct_by_ipca: true, answers_mode: "TODAY" },
    version: 2,
    origin_id: 4,
    created_at: "2026-11-05T10:00:00Z",
    status: "DONE",
    chapters: [
      chapter("PAST", { seal: { level: 3, label: "Confiável", text: "O resultado se manteve em 9 das 12 variantes de regra." } }),
      chapter("FUTURE", { seal: { level: 3, label: "Confiável, um pouco otimista", text: "Quando o modelo disse 90%, aconteceu em 87% das vezes." } }),
    ],
    conclusion: "Suas regras teriam funcionado: R$ 38 mil acima do CDI desde 2012.",
    actions: [
      { kind: "VARIATION", label: "Simular aporte de R$ 2 mil/mês", changes: { monthly_contribution: 1800 } },
      { kind: "COMPARE_ASSET", label: "Estudar TAEE11 no comparador", ticker: "TAEE11", changes: {} },
      { kind: "CONTRIBUTE", label: "Ir para Aportar", changes: {} },
    ],
    notes: ["O capítulo 3 (O que pode melhorar) não rodou: sem candidatos."],
    goal_probability: 0.64,
    goal_target: 1_200_000,
    ...overrides,
  };
}

describe("new study form", () => {
  it("builds the request from the premises and rejects what is missing", () => {
    expect(toStudyRequest({ ...INITIAL_STUDY, label: " " })).toBe("Dê um nome ao estudo.");
    expect(toStudyRequest({ ...INITIAL_STUDY, label: "X", monthly: "0" })).toBe("Informe um aporte mensal maior que zero.");
    expect(toStudyRequest({ ...INITIAL_STUDY, label: "X", horizonYears: "40" })).toBe("Informe um horizonte de 1 a 30 anos.");
    const body = toStudyRequest({ ...INITIAL_STUDY, label: "Aposentadoria", monthly: "1.500,00", wealthGoal: "1.200.000", fixedWeight: true, weightPct: "8" });
    expect(body).toMatchObject({
      label: "Aposentadoria",
      question: "COMPLETE",
      monthly_contribution: 1500,
      wealth_goal: 1_200_000,
      answers_mode: "TODAY",
      weight_mode: "FIXED",
      fixed_weight: 0.08,
    });
  });

  it("reads thousands typed with dots", () => {
    expect(toStudyRequest({ ...INITIAL_STUDY, label: "X", wealthGoal: "1.200.000" })).toMatchObject({ wealth_goal: 1_200_000 });
    expect(toStudyRequest({ ...INITIAL_STUDY, label: "X", monthly: "1.5" })).toMatchObject({ monthly_contribution: 1.5 });
  });

  it("lists only the chapters of the chosen question", () => {
    expect(reviewItems({ ...INITIAL_STUDY, question: "GOAL" }).map((i) => i.title)).toEqual(["Para onde vamos"]);
    expect(reviewItems(INITIAL_STUDY).map((i) => i.title)).toEqual(["De onde viemos", "Para onde vamos", "O que pode melhorar"]);
    expect(premisesLine({ monthly_contribution: 1500, correct_by_ipca: true, horizon_years: 15 })).toMatch(/R\$\s1\.500,00\/mês reajustado pelo IPCA · 15 anos/);
  });

  it("walks the three steps and runs the study", async () => {
    const { calls } = mockApi([
      { method: "POST", path: "/studies", reply: { status: 202, json: study({ status: "PENDING", conclusion: null }) } },
      { path: "/studies/5", reply: study({ status: "PENDING", conclusion: null }) },
      { path: "/studies/5/versions", reply: [] },
    ]);
    renderAt("/tools/simulation/new");
    fireEvent.click(screen.getByRole("radio", { name: /Vou chegar à minha meta/ }));
    fireEvent.click(screen.getByRole("button", { name: "Premissas →" }));
    fireEvent.click(screen.getByRole("button", { name: "Revisar →" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Dê um nome ao estudo.");
    fireEvent.change(screen.getByLabelText("Nome do estudo"), { target: { value: "Aposentadoria 2040" } });
    // GOAL has no past chapter, so the past premises are not asked.
    expect(screen.queryByLabelText("Checklist no passado")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Revisar →" }));
    expect(screen.getByText(/milhares de futuros possíveis em 15 anos/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Rodar estudo" }));
    await waitFor(() => expect(last(calls, "POST", "/studies")?.body).toMatchObject({ label: "Aposentadoria 2040", question: "GOAL" }));
    expect(await screen.findByRole("heading", { name: "Aposentadoria 2040" })).toBeInTheDocument();
  });
});

describe("studies list", () => {
  it("leads with the latest study and its goal chance", async () => {
    mockApi([{ path: "/studies", reply: [summary(), summary({ id: 6, label: "Rodando", status: "RUNNING", chapters_done: 1, headline: null, goal_probability: null })] }]);
    renderAt("/tools/simulation");
    const highlight = await screen.findByRole("region", { name: "Estudo principal" });
    expect(highlight).toHaveTextContent("64%");
    expect(highlight).toHaveTextContent("+3 p.p. desde a versão anterior");
    expect(screen.getByRole("progressbar", { name: "Capítulos prontos" })).toHaveAttribute("aria-valuenow", "1");
    expect(screen.getByRole("link", { name: "+ Novo estudo" })).toHaveAttribute("href", "/tools/simulation/new");
  });

  it("explains how it works without studies", async () => {
    mockApi([{ path: "/studies", reply: [] }]);
    renderAt("/tools/simulation");
    expect(await screen.findByText("Nenhum estudo ainda")).toBeInTheDocument();
    expect(screen.getByRole("note", { name: "Como funciona" })).toBeInTheDocument();
  });
});

describe("study page", () => {
  it("tells the conclusion, the seals and the next steps", async () => {
    const { calls } = mockApi([
      { path: "/studies/5", reply: study() },
      { path: "/studies/5/versions", reply: [{ id: 4, version: 1, status: "DONE", goal_probability: 0.61 }, { id: 5, version: 2, status: "DONE", goal_probability: 0.64 }] },
      { method: "POST", path: "/studies/5/variations", reply: { status: 202, json: study({ id: 7, label: "Aposentadoria 2040 · aporte R$ 2 mil", variation_of: 5 }) } },
      { path: "/studies/7", reply: study({ id: 7, label: "Aposentadoria 2040 · aporte R$ 2 mil", variation_of: 5 }) },
      { path: "/studies/7/versions", reply: [] },
    ]);
    renderAt("/tools/simulation/5");
    const conclusion = await screen.findByRole("region", { name: "Conclusão do estudo" });
    expect(conclusion).toHaveTextContent("R$ 38 mil acima do CDI");
    expect(within(conclusion).getByRole("link", { name: "Estudar TAEE11 no comparador" })).toHaveAttribute("href", expect.stringContaining("TAEE11"));
    expect(screen.getByRole("complementary", { name: "Avisos do estudo" })).toHaveTextContent("capítulo 3");
    const past = screen.getByRole("region", { name: "Capítulo 1, De onde viemos" });
    expect(within(past).getByText("Este capítulo não rodou")).toBeInTheDocument();
    expect(await screen.findByText(/chance da meta 61%/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Comparar com a versão anterior" })).toHaveAttribute("href", "/tools/simulation/compare?a=4&b=5");

    fireEvent.click(within(conclusion).getByRole("button", { name: "Simular aporte de R$ 2 mil/mês" }));
    await waitFor(() => expect(last(calls, "POST", "/studies/5/variations")?.body).toEqual({ changes: { monthly_contribution: 1800 } }));
    expect(await screen.findByRole("heading", { name: "Aposentadoria 2040 · aporte R$ 2 mil" })).toBeInTheDocument();
  });

  it("shows the seal of a finished chapter next to its result", async () => {
    mockApi([
      {
        path: "/studies/5",
        reply: study({ chapters: [chapter("FUTURE", { run_id: 9, status: "DONE", seal: { level: 3, label: "Confiável, um pouco otimista", text: "Quando o modelo disse 90%, aconteceu em 87% das vezes." } })] }),
      },
      { path: "/studies/5/versions", reply: [] },
      { path: "/simulations/9", reply: { id: 9, kind: "PROJECTION", status: "PENDING", params: {}, params_hash: "h", code_version: "41", seed: 7, results: [] } },
    ]);
    renderAt("/tools/simulation/5");
    const seal = await screen.findByRole("complementary", { name: "Quanto confiar nestas chances?" });
    expect(seal).toHaveTextContent("●●●○");
    expect(seal).toHaveTextContent("aconteceu em 87%");
    expect(within(seal).getByRole("link", { name: /qualidade dos modelos/ })).toHaveAttribute("href", "/tools/simulation/quality");
  });

  it("deletes the study for good after asking", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { calls } = mockApi([
      { path: "/studies/5", reply: study() },
      { path: "/studies/5/versions", reply: [] },
      { method: "DELETE", path: "/studies/5", reply: { status: 204 } },
      { path: "/studies", reply: [] },
    ]);
    renderAt("/tools/simulation/5");
    fireEvent.click(await screen.findByRole("button", { name: "Excluir estudo" }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/não há como recuperar/));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/studies/5")).toBe(true));
    expect(await screen.findByText("Nenhum estudo ainda")).toBeInTheDocument();
  });
});

describe("compare studies", () => {
  it("puts two studies side by side with the premises that differ", async () => {
    const comparison: StudyComparisonDTO = {
      a: study(),
      b: study({ id: 7, label: "Aporte R$ 1.800" }),
      headline: "Mudando aporte mensal, a chance da meta vai de 64% para 71% (+7 p.p.).",
      differences: [{ key: "monthly_contribution", label: "Aporte mensal", a: 1500, b: 1800 }],
      rows: [
        { chapter: "PAST", label: "Acima do CDI", a: "R$ 38 mil", b: "R$ 38 mil", difference: "igual", tone: "neutral" },
        { chapter: "FUTURE", label: "Chance da meta", a: "64%", b: "71%", difference: "+7 p.p.", tone: "positive" },
      ],
    };
    mockApi([
      { path: "/studies", reply: [summary(), summary({ id: 7, label: "Aporte R$ 1.800" })] },
      { path: "/studies/compare", reply: comparison },
    ]);
    renderAt("/tools/simulation/compare?a=5&b=7");
    expect(await screen.findByRole("note", { name: "Em resumo" })).toHaveTextContent("de 64% para 71%");
    expect(screen.getByText(/aporte mensal 1500 → 1800/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Comparação dos estudos" });
    expect(within(table).getByText("Capítulo 2 · Para onde vamos")).toBeInTheDocument();
    expect(within(table).getByText("+7 p.p.")).toHaveClass("app-positive");
  });
});

describe("Home card", () => {
  it("shows the latest finished study and its goal chance", async () => {
    mockApi([{ path: "/studies", reply: [summary({ id: 6, status: "RUNNING" }), summary()] }]);
    render(
      <MemoryRouter>
        <LatestStudy />
      </MemoryRouter>,
    );
    const card = await screen.findByRole("region", { name: "Último estudo" });
    expect(card).toHaveTextContent("64%de chance de chegar à meta");
    expect(within(card).getByRole("link", { name: "Abrir o estudo →" })).toHaveAttribute("href", "/tools/simulation/5");
  });
});
