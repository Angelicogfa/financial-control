"""Use cases of the Garimpo (Phase 43): read what the worker stored."""

from __future__ import annotations

from controllers.research.responses import (
    MiningFindingDTO,
    MiningMemberDTO,
    MiningOverviewDTO,
    MiningRecordDTO,
    MiningRecordLineDTO,
    MiningSignalWeightDTO,
    MiningUniverseDTO,
    MiningWhyDTO,
)
from controllers.shared.dependencies import UoWFactory
from domain.disclosures.services.sync import base_ticker
from domain.forecast.valuation_model import month_of
from domain.mining.findings import RecordLine, ranking_weights
from domain.mining.model import FINDINGS, MiningModel, ranking
from domain.mining.runs import MINING
from domain.mining.signals import IMPROVEMENT, MOMENTUM, QUALITY, SIGNALS, VALUE
from domain.mining.universe import MIN_DAILY_VOLUME, mining_universe
from domain.shared.enums import AssetType
from domain.simulation.data import px_symbol

_WORDS = {
    VALUE: "valor",
    QUALITY: "qualidade",
    IMPROVEMENT: "melhora dos resultados",
    MOMENTUM: "momentum",
}


def _annual(monthly: float) -> float:
    return round((1.0 + monthly) ** 12 - 1.0, 6)


def _record_dto(line: dict) -> MiningRecordLineDTO:
    item = RecordLine(**line)
    return MiningRecordLineDTO(
        horizon=item.horizon,
        trusted=item.trusted,
        runs=item.runs,
        findings=item.findings,
        beat=item.beat,
        beat_share=round(item.beat_share, 4),
        beat_low=item.beat_low,
        beat_high=item.beat_high,
        mean_excess_annual=_annual(item.mean_excess),
    )


class MiningHandler:
    def __init__(self, uow_factory: UoWFactory, min_daily_volume: float = MIN_DAILY_VOLUME) -> None:
        self.uow_factory = uow_factory
        self.min_daily_volume = min_daily_volume

    def universe(self) -> MiningUniverseDTO:
        """The liquid stocks the mining looks at, and how far their stored history goes."""
        with self.uow_factory() as uow:
            members = mining_universe(uow, self.min_daily_volume)
            ranges = {m.ticker: uow.market_series.date_range(px_symbol(m.ticker)) for m in members}
            with_statements = uow.cvm_statements.cnpjs_with_statements()
        items = [
            MiningMemberDTO(
                ticker=m.ticker,
                company=m.company,
                sector=m.sector,
                daily_volume=m.daily_volume,
                volume_source=m.volume_source,  # type: ignore[arg-type]
                history_from=ranges[m.ticker][0] if ranges[m.ticker] else None,
                history_to=ranges[m.ticker][1] if ranges[m.ticker] else None,
                has_statements=m.cnpj in with_statements,
            )
            for m in members
        ]
        return MiningUniverseDTO(
            min_daily_volume=self.min_daily_volume,
            members=items,
            with_history=sum(1 for i in items if i.history_to is not None),
            with_statements=sum(1 for i in items if i.has_statements),
        )

    def _model(self, uow: object) -> MiningModel | None:
        stored = uow.forecasts.latest_model(MINING)  # type: ignore[attr-defined]
        return MiningModel.from_dict(stored.payload) if stored is not None else None

    def overview(self) -> MiningOverviewDTO:
        with self.uow_factory() as uow:
            model = self._model(uow)
            findings = uow.mining.findings()
            catalog = {i.ticker.upper(): i for i in uow.catalog.list_all()}
            assets = {a.ticker.upper(): a.id for a in uow.assets.list_all(active_only=True)}
        if model is None:
            return MiningOverviewDTO(
                status="NOT_RUN",
                reason="O garimpo ainda não rodou; ele roda uma vez por semana, depois dos "
                "balanços e do histórico.",
            )
        return MiningOverviewDTO(
            status="OK",
            found_on=findings[0].found_on if findings else model.as_of,
            month=findings[0].month if findings else None,
            trusted=model.passed,
            reason=model.reason,
            oos_months=model.oos_months,
            oos_excess_annual=model.oos_excess_annual,
            oos_probability=model.oos_probability,
            oos_hit_rate=model.oos_hit_rate,
            pbo=model.pbo,
            loss_probability=model.loss_probability,
            variants=model.variants,
            cost_annual=model.cost_annual,
            weights=[
                MiningSignalWeightDTO(
                    signal=s.signal,  # type: ignore[arg-type]
                    estimate_annual_per_z=_annual(s.estimate),
                    weight_annual_per_z=_annual(s.weight),
                    sign_probability=s.sign_probability,
                    used=s.weight != 0,
                )
                for s in model.signals
            ],
            findings=[
                MiningFindingDTO(
                    rank=f.rank,
                    ticker=f.ticker,
                    company=catalog[f.ticker].name if f.ticker in catalog else "",
                    sector=(catalog[f.ticker].sector or "") if f.ticker in catalog else "",
                    score_annual=_annual(f.score),
                    signals=f.signals,
                    reason=f.reason,
                    asset_id=assets.get(f.ticker),
                )
                for f in findings
            ],
            record=[_record_dto(line) for line in model.record],
        )

    def record(self) -> MiningRecordDTO:
        return MiningRecordDTO(lines=self.overview().record)

    def why(self, ticker: str) -> MiningWhyDTO:
        code = ticker.strip().upper()
        with self.uow_factory() as uow:
            model = self._model(uow)
            members = {m.ticker: m for m in mining_universe(uow, self.min_daily_volume)}
            month = uow.mining.latest_signal_month()
            findings = uow.mining.findings()
            signals = uow.mining.signals_of_month(findings[0].month) if findings else []
            instrument = next((i for i in uow.catalog.list_all() if i.ticker.upper() == code), None)
            mapped = bool(uow.cvm_issuers.cnpjs_for([base_ticker(code)]))
            with_history = uow.market_series.date_range(px_symbol(code)) is not None
        if model is None or month is None:
            return MiningWhyDTO(
                ticker=code, status="NOT_RUN", reasons=["O garimpo ainda não rodou."]
            )
        if code not in members:
            reasons = []
            if instrument is None or instrument.asset_type != AssetType.STOCK_BR:
                reasons.append("Não é uma ação brasileira do catálogo da B3.")
            elif not mapped:
                reasons.append("Não tem código no cadastro da CVM: sem balanços para medir.")
            else:
                reasons.append(
                    "Liquidez abaixo do piso do garimpo, ou outra classe da mesma empresa "
                    "é mais negociada e a representa."
                )
            return MiningWhyDTO(ticker=code, status="NOT_IN_UNIVERSE", reasons=reasons)
        panel: dict[str, dict] = {}
        for s in signals:
            if s.signal not in SIGNALS:  # the panel also keeps the recommendation's signals
                continue
            panel.setdefault(s.ticker, {}).setdefault(month_of(s.month), {})[s.signal] = s.z
        weights = ranking_weights(model)
        key = month_of(findings[0].month) if findings else None
        ranked = ranking(panel, key, weights) if key else []
        position = next((i for i, (t, _v) in enumerate(ranked, start=1) if t == code), None)
        if position is None:
            missing = [] if with_history else ["Ainda sem histórico de preço guardado."]
            return MiningWhyDTO(
                ticker=code,
                status="NO_SIGNALS",
                reasons=missing or ["Sem balanço recente ou sem preço no mês dos sinais."],
            )
        values = panel[code][key]
        score = ranked[position - 1][1]
        cutoff = ranked[min(FINDINGS, len(ranked)) - 1][1]
        reasons = []
        for name, weight in sorted(weights.items(), key=lambda w: -abs(w[1])):
            z = values.get(name)
            if z is None:
                reasons.append(f"Sem sinal de {_WORDS[name]}.")
            elif weight * z < 0:
                reasons.append(
                    f"O sinal de {_WORDS[name]} pesou contra (z {z:+.1f}).".replace(".", ",", 1)
                )
        return MiningWhyDTO(
            ticker=code,
            status="FOUND" if position <= FINDINGS else "RANKED",
            rank=position,
            ranked=len(ranked),
            score_annual=_annual(score),
            cutoff_annual=_annual(cutoff),
            signals={k: round(v, 3) for k, v in values.items()},
            reasons=reasons,
        )
