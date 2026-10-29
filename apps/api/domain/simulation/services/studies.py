"""Use cases of the simulation studies (Phase 41).

A study queues one run per chapter through the Phase 33 submitters, links them to the study and,
when they finish, reads their results to tell the story: a lead and a "quanto confiar" seal per
chapter, then the conclusion with its next steps. The engines themselves do not change.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from controllers.shared.dependencies import UoWFactory
from controllers.simulation.requests import (
    BacktestRequest,
    CandidatesRequest,
    ProjectionRequest,
    StudyRequest,
    StudyVariationRequest,
)
from controllers.simulation.responses import (
    CalibrationDTO,
    CandidatesDTO,
    ProjectionDTO,
    RobustnessDTO,
    SimulationRunDetailDTO,
    StudyActionDTO,
    StudyChapterDTO,
    StudyComparisonDTO,
    StudyComparisonRowDTO,
    StudyDifferenceDTO,
    StudyDTO,
    StudySealDTO,
    StudySummaryDTO,
    StudyVersionDTO,
)
from core.errors import DomainError, NotFoundError, ValidationError
from domain.simulation.entities import SimulationRun, SimulationStatus, SimulationStudy
from domain.simulation.services.use_cases import SimulationHandler
from domain.simulation.studies import (
    CHAPTER_TITLES,
    CHAPTERS_BY_QUESTION,
    QUESTION_LABELS,
    Chapter,
    FutureFacts,
    ImproveFacts,
    PastFacts,
    Seal,
    StudyPremises,
    conclusion,
    confidence_seal,
    future_lead,
    improve_lead,
    money,
    past_lead,
    pct,
    points,
    premise_differences,
    robustness_seal,
    with_label,
)

ACTIVE = (SimulationStatus.PENDING, SimulationStatus.RUNNING)
FAILED = (SimulationStatus.FAILED, SimulationStatus.TIMEOUT)


def _seal_dto(seal: Seal | None) -> StudySealDTO | None:
    return StudySealDTO(level=seal.level, label=seal.label, text=seal.text) if seal else None


class _Chapters:
    """The facts and seals read from the finished runs of one study."""

    def __init__(self) -> None:
        self.past: PastFacts | None = None
        self.past_seal: Seal | None = None
        self.future: FutureFacts | None = None
        self.future_seal: Seal | None = None
        self.improve: ImproveFacts | None = None


class StudyHandler:
    def __init__(self, uow_factory: UoWFactory, simulations: SimulationHandler) -> None:
        self.uow_factory = uow_factory
        self.simulations = simulations

    # --- commands ---------------------------------------------------------------------------

    def create(self, req: StudyRequest, *, today: date | None = None) -> StudyDTO:
        premises = StudyPremises.from_dict(
            {
                **req.model_dump(exclude={"label", "question", "past_start"}),
                **({"past_start": req.past_start.isoformat()} if req.past_start else {}),
            }
        )
        study = SimulationStudy(
            label=req.label.strip(), question=req.question, premises=premises.to_dict()
        )
        return self._start(study, premises, today=today)

    def refresh(self, study_id: int, *, today: date | None = None) -> StudyDTO:
        """The same premises with today's data and portfolio: a new version of the study."""
        with self.uow_factory() as uow:
            current = self._get(uow, study_id)
            origin = current.origin_id or current.id
            assert origin is not None
            version = max(s.version for s in uow.simulation_studies.versions(origin)) + 1
        study = SimulationStudy(
            label=current.label,
            question=current.question,
            premises=current.premises,
            version=version,
            origin_id=origin,
            variation_of=current.variation_of,
        )
        return self._start(study, StudyPremises.from_dict(current.premises), today=today)

    def variation(
        self, study_id: int, req: StudyVariationRequest, *, today: date | None = None
    ) -> StudyDTO:
        """A copy with some premises changed, ready to compare with the original."""
        with self.uow_factory() as uow:
            source = self._get(uow, study_id)
        base = StudyPremises.from_dict(source.premises)
        try:
            premises = base.with_changes(dict(req.changes))
            StudyRequest(label=source.label, question=source.question, **premises.to_dict())  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"invalid premise change: {exc}", code="INVALID_PREMISES"
            ) from exc
        label = req.label or f"{source.label} · {with_label(premises, dict(req.changes))}"
        study = SimulationStudy(
            label=label[:120],
            question=source.question,
            premises=premises.to_dict(),
            variation_of=source.id,
        )
        return self._start(study, premises, today=today)

    def delete(self, study_id: int, *, now: datetime | None = None) -> None:
        """Delete a study and its runs for good (logical deletion, no restore)."""
        at = now or datetime.now(UTC)
        with self.uow_factory() as uow:
            self._get(uow, study_id)
            for run in uow.simulations.list_for_study(study_id):
                if run.id is not None:
                    uow.simulations.mark_deleted(run.id, deleted_at=at)
            uow.simulation_studies.mark_deleted(study_id, deleted_at=at)
            uow.commit()

    # --- queries ----------------------------------------------------------------------------

    def get(self, study_id: int) -> StudyDTO:
        with self.uow_factory() as uow:
            study = self._get(uow, study_id)
            runs = uow.simulations.list_for_study(study_id)
        return self._build(study, runs)[0]

    def list(self, limit: int = 50) -> list[StudySummaryDTO]:
        with self.uow_factory() as uow:
            studies = uow.simulation_studies.list_recent(limit)
            runs = {s.id: uow.simulations.list_for_study(s.id) for s in studies if s.id}
            previous: dict[int, SimulationStudy | None] = {}
            for s in studies:
                if s.id is not None and s.origin_id is not None:
                    older = [
                        v for v in uow.simulation_studies.versions(s.origin_id) if v.id != s.id
                    ]
                    previous[s.id] = older[-1] if older else None
            previous_runs = {
                p.id: uow.simulations.list_for_study(p.id)
                for p in previous.values()
                if p is not None and p.id is not None
            }
        rows = []
        for s in studies:
            assert s.id is not None
            dto, _ = self._build(s, runs.get(s.id, []), with_story=False)
            change = None
            before = previous.get(s.id)
            if before is not None and before.id is not None and dto.goal_probability is not None:
                old, _ = self._build(before, previous_runs.get(before.id, []), with_story=False)
                if old.goal_probability is not None:
                    change = round(dto.goal_probability - old.goal_probability, 4)
            headline = dto.chapters[0].lead if dto.chapters and dto.chapters[0].lead else None
            future = next((c for c in dto.chapters if c.key == Chapter.FUTURE), None)
            if future is not None and future.lead:
                headline = future.lead
            rows.append(
                StudySummaryDTO(
                    id=s.id,
                    label=s.label,
                    question=s.question,
                    question_label=dto.question_label,
                    version=s.version,
                    variation_of=s.variation_of,
                    created_at=s.created_at,
                    status=dto.status,
                    chapters_done=sum(1 for c in dto.chapters if c.status == SimulationStatus.DONE),
                    chapters_total=len(dto.chapters),
                    headline=headline,
                    goal_probability=dto.goal_probability,
                    goal_target=dto.goal_target,
                    goal_change=change,
                )
            )
        return rows

    def versions(self, study_id: int) -> list[StudyVersionDTO]:
        with self.uow_factory() as uow:
            study = self._get(uow, study_id)
            family = uow.simulation_studies.versions(study.origin_id or study_id)
            runs = {v.id: uow.simulations.list_for_study(v.id) for v in family if v.id}
        out = []
        for v in family:
            assert v.id is not None
            dto, _ = self._build(v, runs.get(v.id, []), with_story=False)
            out.append(
                StudyVersionDTO(
                    id=v.id,
                    version=v.version,
                    created_at=v.created_at,
                    status=dto.status,
                    goal_probability=dto.goal_probability,
                )
            )
        return out

    def compare(self, a_id: int, b_id: int) -> StudyComparisonDTO:
        with self.uow_factory() as uow:
            a = self._get(uow, a_id)
            b = self._get(uow, b_id)
            runs_a = uow.simulations.list_for_study(a_id)
            runs_b = uow.simulations.list_for_study(b_id)
        dto_a, facts_a = self._build(a, runs_a)
        dto_b, facts_b = self._build(b, runs_b)
        prem_a, prem_b = StudyPremises.from_dict(a.premises), StudyPremises.from_dict(b.premises)
        differences = [
            StudyDifferenceDTO(key=k, label=label, a=va, b=vb)
            for k, label, va, vb in premise_differences(prem_a, prem_b)
        ]
        rows = _comparison_rows(facts_a, facts_b)
        return StudyComparisonDTO(
            a=dto_a,
            b=dto_b,
            headline=_comparison_headline(dto_a, dto_b, differences),
            differences=differences,
            rows=rows,
        )

    # --- internals --------------------------------------------------------------------------

    @staticmethod
    def _get(uow: Any, study_id: int) -> SimulationStudy:
        study = uow.simulation_studies.get(study_id)
        if study is None:
            raise NotFoundError(f"Simulation study {study_id} not found")
        return study

    def _start(
        self, study: SimulationStudy, premises: StudyPremises, *, today: date | None = None
    ) -> StudyDTO:
        with self.uow_factory() as uow:
            stored = uow.simulation_studies.add(study)
            uow.commit()
        assert stored.id is not None
        notes = self._launch(stored, premises, today=today)
        if notes:
            with self.uow_factory() as uow:
                current = self._get(uow, stored.id)
                uow.simulation_studies.update(
                    SimulationStudy(**{**current.__dict__, "notes": [*current.notes, *notes]})
                )
                uow.commit()
        return self.get(stored.id)

    def _launch(
        self, study: SimulationStudy, premises: StudyPremises, *, today: date | None = None
    ) -> list[str]:
        """Queue the chapter runs in order (the worker serves them oldest first)."""
        assert study.id is not None
        chapters = CHAPTERS_BY_QUESTION.get(study.question, CHAPTERS_BY_QUESTION["COMPLETE"])
        end = (today or date.today()) - timedelta(days=1)
        notes: list[str] = []
        for chapter in chapters:
            number, title, _question = CHAPTER_TITLES[chapter]
            label = f"{study.label} · {title}"[:120]
            try:
                if chapter == Chapter.PAST:
                    run = self.simulations.submit_backtest(
                        BacktestRequest(
                            start=premises.past_start,
                            end=end,
                            monthly_contribution=premises.monthly_contribution,
                            correct_by_ipca=premises.correct_by_ipca,
                            rebalance=premises.rebalance,
                            policy_mode=premises.policy_mode,  # type: ignore[arg-type]
                            benchmarks=list(premises.benchmarks),  # type: ignore[arg-type]
                            variants=True,
                            answers_mode=premises.answers_mode,  # type: ignore[arg-type]
                            label=label,
                        ),
                        today=today,
                    )
                elif chapter == Chapter.FUTURE:
                    run = self.simulations.submit_projection(
                        ProjectionRequest(
                            horizon_years=premises.horizon_years,
                            monthly_contribution=premises.monthly_contribution,
                            wealth_goal=premises.wealth_goal,
                            rebalance=premises.rebalance,
                            label=label,
                        )
                    )
                else:
                    run = self.simulations.submit_candidates(
                        CandidatesRequest(
                            horizon_years=min(premises.horizon_years, 30),
                            monthly_contribution=premises.monthly_contribution,
                            wealth_goal=premises.wealth_goal,
                            rebalance=premises.rebalance,
                            include_screener=premises.include_screener,
                            weight_mode=premises.weight_mode,  # type: ignore[arg-type]
                            fixed_weight=premises.fixed_weight,
                            rupture_stress=premises.rupture_stress,
                            label=label,
                        )
                    )
            except DomainError as exc:
                notes.append(f"O capítulo {number} ({title}) não rodou: {exc}")
                continue
            with self.uow_factory() as uow:
                uow.simulations.attach(run.id, study_id=study.id, chapter=chapter)
                uow.commit()
        return notes

    def _build(
        self, study: SimulationStudy, runs: list[SimulationRun], *, with_story: bool = True
    ) -> tuple[StudyDTO, _Chapters]:
        assert study.id is not None
        premises = StudyPremises.from_dict(study.premises)
        wanted = CHAPTERS_BY_QUESTION.get(study.question, CHAPTERS_BY_QUESTION["COMPLETE"])
        by_chapter = {r.chapter: r for r in runs if r.chapter}
        facts = _Chapters()
        chapters: list[StudyChapterDTO] = []
        for key in wanted:
            number, title, question = CHAPTER_TITLES[key]
            run = by_chapter.get(key)
            chapter = StudyChapterDTO(
                key=key,  # type: ignore[arg-type]
                number=number,
                title=title,
                question=question,
                run_id=run.id if run else None,
                status=run.status if run else None,
                error=run.error if run else None,
            )
            if run is not None and run.status == SimulationStatus.DONE and run.id is not None:
                chapter = self._tell(chapter, key, run.id, premises, facts, with_story)
            chapters.append(chapter)

        statuses = [c.status for c in chapters]
        if statuses and all(s == SimulationStatus.DONE for s in statuses):
            status = "DONE"
        elif any(s in ACTIVE for s in statuses):
            status = (
                "RUNNING" if any(s == SimulationStatus.RUNNING for s in statuses) else "PENDING"
            )
        elif any(s == SimulationStatus.DONE for s in statuses):
            status = "PARTIAL"
        else:
            status = "FAILED"

        text, actions = None, []
        if with_story and status in ("DONE", "PARTIAL"):
            text, found = conclusion(
                premises,
                facts.past,
                facts.past_seal,
                facts.future,
                facts.future_seal,
                facts.improve,
            )
            actions = [
                StudyActionDTO(kind=a.kind, label=a.label, ticker=a.ticker, changes=a.changes)  # type: ignore[arg-type]
                for a in found
            ]
        future = facts.future
        dto = StudyDTO(
            id=study.id,
            label=study.label,
            question=study.question,
            question_label=QUESTION_LABELS.get(study.question, study.question),
            premises=premises.to_dict(),
            version=study.version,
            origin_id=study.origin_id,
            variation_of=study.variation_of,
            created_at=study.created_at,
            status=status,  # type: ignore[arg-type]
            chapters=chapters,
            conclusion=text or None,
            actions=actions,
            notes=list(study.notes),
            goal_probability=future.probability if future else None,
            goal_target=future.target if future else None,
        )
        return dto, facts

    def _tell(
        self,
        chapter: StudyChapterDTO,
        key: str,
        run_id: int,
        premises: StudyPremises,
        facts: _Chapters,
        with_story: bool,
    ) -> StudyChapterDTO:
        """Lead and seal of a finished chapter; the facts feed the conclusion."""
        if key == Chapter.PAST:
            facts.past = past_facts(self.simulations.get_run(run_id), premises)
            if facts.past is None:
                return chapter
            notes = (
                [
                    "As respostas do checklist de hoje foram aplicadas ao período inteiro: isso "
                    "usa informação que não existia na época e pode deixar o passado melhor do "
                    "que foi."
                ]
                if facts.past.answers_today
                else []
            )
            if with_story:
                facts.past_seal = past_seal(self.simulations.robustness(run_id), facts.past)
            lead = past_lead(facts.past)
            return chapter.model_copy(
                update={
                    "lead": lead.text,
                    "tone": lead.tone,
                    "seal": _seal_dto(facts.past_seal),
                    "notes": notes,
                }
            )
        if key == Chapter.FUTURE:
            facts.future = future_facts(self.simulations.projection(run_id), premises)
            if facts.future is None:
                return chapter
            if with_story:
                facts.future_seal = future_seal(self.simulations.calibration())
            lead = future_lead(facts.future)
            return chapter.model_copy(
                update={"lead": lead.text, "tone": lead.tone, "seal": _seal_dto(facts.future_seal)}
            )
        if not with_story:
            return chapter
        facts.improve = improve_facts(self.simulations.candidates(run_id))
        if facts.improve is None:
            return chapter
        lead = improve_lead(facts.improve)
        return chapter.model_copy(
            update={
                "lead": lead.text,
                "tone": lead.tone,
                "seal": _seal_dto(facts.future_seal),
                "notes": ["É uma lista para estudo, nunca uma ordem de compra."],
            }
        )


# --- reading the run results ----------------------------------------------------------------------


def past_facts(detail: SimulationRunDetailDTO, premises: StudyPremises) -> PastFacts | None:
    by_key = {r.key: r for r in detail.results}
    strategy = by_key.get("strategy")
    if strategy is None:
        return None
    cdi = by_key.get("benchmark:CDI")
    references = [r for k, r in by_key.items() if k.startswith("benchmark:")]
    best = max(references, key=lambda r: r.summary.final_value, default=None)
    return PastFacts(
        final_value=strategy.summary.final_value,
        contributed=strategy.summary.contributed,
        cdi_final=cdi.summary.final_value if cdi else None,
        best_label=best.label if best else None,
        best_final=best.summary.final_value if best else None,
        annual_irr=strategy.summary.money_weighted_return,
        max_drawdown=strategy.summary.max_drawdown,
        answers_today=detail.params.get("answers_mode") == "TODAY",
    )


def past_seal(robustness: RobustnessDTO, past: PastFacts) -> Seal:
    worst: tuple[str, float] | None = None
    for crisis in robustness.crises:
        outcome = crisis.outcomes.get("strategy")
        if (
            outcome
            and outcome.covered
            and outcome.max_drawdown is not None
            and (worst is None or outcome.max_drawdown < worst[1])
        ):
            worst = (crisis.label, outcome.max_drawdown)
    variants = robustness.variants
    if past.cdi_final is None or not variants:
        return robustness_seal(0, 0, worst)
    beats = past.final_value >= past.cdi_final
    agreeing = sum(1 for v in variants if (v.summary.final_value >= past.cdi_final) == beats)
    return robustness_seal(agreeing, len(variants), worst)


def future_facts(projection: ProjectionDTO, premises: StudyPremises) -> FutureFacts | None:
    if not projection.scenarios:
        return None
    scenario = next((s for s in projection.scenarios if s.key == "BASE"), projection.scenarios[0])
    end_year = (date.today() + timedelta(days=round(scenario.horizon_months * 30.44))).year
    goal = scenario.wealth_goal
    return FutureFacts(
        end_year=end_year,
        p50=scenario.final_wealth.p50,
        p5=scenario.final_wealth.p5,
        target=goal.target if goal else None,
        probability=goal.probability if goal else None,
        low=goal.low if goal else None,
        high=goal.high if goal else None,
    )


def future_seal(calibration: CalibrationDTO) -> Seal:
    stacked = next((g for g in calibration.generators if g.key == "STACKED"), None)
    if stacked is None:
        return confidence_seal(None, 0.0, None, None)
    when = calibration.finished_at.date() if calibration.finished_at else None
    return confidence_seal(stacked.coverage, stacked.effective_windows, stacked.status, when)


def improve_facts(candidates: CandidatesDTO) -> ImproveFacts | None:
    if not candidates.candidates and candidates.evaluated == 0:
        return None
    base_goal = candidates.base.goal_probability if candidates.base else None

    def helps(c: Any) -> bool:
        gain = (
            c.effect.delta_goal_probability
            if c.effect.delta_goal_probability is not None
            else c.effect.delta_final_wealth
        )
        return c.effect.p_improve >= 0.5 and gain > 0

    ranked = sorted(candidates.candidates, key=lambda c: c.effect.rank or 10_000)
    improving = [c for c in ranked if helps(c)]
    best = improving[0] if improving else None
    new_goal = (
        base_goal + best.effect.delta_goal_probability
        if best is not None
        and base_goal is not None
        and best.effect.delta_goal_probability is not None
        else None
    )
    return ImproveFacts(
        evaluated=candidates.evaluated or len(candidates.candidates),
        improving=len(improving),
        ticker=best.ticker if best else None,
        base_probability=base_goal if best else None,
        new_probability=new_goal,
        p_improve=best.effect.p_improve if best else None,
        delta_wealth=best.effect.delta_final_wealth if best else None,
    )


# --- comparison -----------------------------------------------------------------------------------


def _row(
    chapter: str, label: str, a: float | None, b: float | None, kind: str
) -> StudyComparisonRowDTO:
    def show(v: float | None) -> str:
        if v is None:
            return "—"
        return pct(v) if kind == "pct" else money(v)

    if a is None or b is None:
        diff, tone = "—", "neutral"
    elif abs(b - a) < 1e-9:
        diff, tone = "igual", "neutral"
    else:
        diff = points(b - a) if kind == "pct" else ("+" if b > a else "") + money(b - a)
        tone = "positive" if b > a else "negative"
    return StudyComparisonRowDTO(
        chapter=chapter,  # type: ignore[arg-type]
        label=label,
        a=show(a),
        b=show(b),
        difference=diff,
        tone=tone,
    )


def _over_cdi(f: PastFacts | None) -> float | None:
    return f.final_value - f.cdi_final if f and f.cdi_final is not None else None


def _comparison_rows(a: _Chapters, b: _Chapters) -> list[StudyComparisonRowDTO]:
    rows: list[StudyComparisonRowDTO] = []
    if a.past or b.past:
        gap = _over_cdi
        rows.append(_row(Chapter.PAST, "Acima do CDI", gap(a.past), gap(b.past), "money"))
        rows.append(
            _row(
                Chapter.PAST,
                "Patrimônio final",
                a.past.final_value if a.past else None,
                b.past.final_value if b.past else None,
                "money",
            )
        )
    if a.future or b.future:
        rows.append(
            _row(
                Chapter.FUTURE,
                "Chance da meta",
                a.future.probability if a.future else None,
                b.future.probability if b.future else None,
                "pct",
            )
        )
        rows.append(
            _row(
                Chapter.FUTURE,
                "Patrimônio mediano",
                a.future.p50 if a.future else None,
                b.future.p50 if b.future else None,
                "money",
            )
        )
        rows.append(
            _row(
                Chapter.FUTURE,
                "5% piores",
                a.future.p5 if a.future else None,
                b.future.p5 if b.future else None,
                "money",
            )
        )
    if a.improve or b.improve:
        ta = a.improve.ticker if a.improve else None
        tb = b.improve.ticker if b.improve else None
        rows.append(
            StudyComparisonRowDTO(
                chapter="IMPROVE",
                label="Candidato mais promissor",
                a=ta or "—",
                b=tb or "—",
                difference="igual" if ta == tb else "diferente",
            )
        )
    return rows


def _comparison_headline(a: StudyDTO, b: StudyDTO, diffs: list[StudyDifferenceDTO]) -> str:
    changed = ", ".join(d.label.lower() for d in diffs) or "nenhuma premissa"
    if a.goal_probability is not None and b.goal_probability is not None:
        return (
            f"Mudando {changed}, a chance da meta vai de {pct(a.goal_probability)} para "
            f"{pct(b.goal_probability)} ({points(b.goal_probability - a.goal_probability)})."
        )
    return f"Os dois estudos diferem em: {changed}."
