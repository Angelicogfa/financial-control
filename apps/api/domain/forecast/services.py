"""Use cases of the price forecasts (Phase 42.1): read what the worker stored.

The screen never computes: it reads the latest forecast of the asset and the latest
calibration, adds the prices that matter to the user (today's, the average paid, the fair
value) and hides the forecast while its confidence is below "Use com cautela" (decision 42.0-5),
unless the user asked for that asset by itself: then it is shown with a warning, from 12 months
of history on.
"""

from __future__ import annotations

from datetime import date, timedelta

from controllers.assets.responses import (
    AssetForecastDTO,
    ForecastDriverDTO,
    ForecastHorizonDTO,
    ForecastProbabilityDTO,
    ForecastQualityDTO,
    ForecastSealDTO,
    ForecastThresholdDTO,
    ForecastValuationDTO,
    ValuationOriginDTO,
)
from controllers.shared.dependencies import UoWFactory
from core.errors import NotFoundError, ValidationError
from domain.forecast.calibration import ForecastCalibration
from domain.forecast.model import FALL_THRESHOLD, PriceForecast, chance_above
from domain.forecast.repositories import StoredCalibration
from domain.forecast.runs import REQUESTED_MIN_MONTHS, VALUATION, refresh_forecasts
from domain.forecast.valuation_model import ValuationModel
from domain.policy.services.policy import current_policy
from domain.portfolio.services.service import PortfolioApplicationService
from domain.simulation.candidates import MIN_HISTORY_MONTHS
from domain.simulation.studies import Seal, confidence_seal, money, pct
from infra.providers.stored import stored_fundamentals, stored_macro_rates, stored_usd_brl

MIN_SEAL_LEVEL = 2  # "Use com cautela" or better (decision 42.0-5)
LEAD_HORIZON = 12


def forecast_seal(stored: StoredCalibration | None) -> Seal:
    if stored is None:
        return confidence_seal(None, 0.0, None, None)
    cal = ForecastCalibration.from_dict(stored.payload)
    return confidence_seal(cal.coverage_90, cal.effective_windows, None, cal.as_of)


def _seal_dto(seal: Seal) -> ForecastSealDTO:
    return ForecastSealDTO(level=seal.level, label=seal.label, text=seal.text)


def _annual(monthly: float) -> float:
    return round((1.0 + monthly) ** 12 - 1.0, 4)


def _valuation_dto(model: ValuationModel) -> ForecastValuationDTO:
    return ForecastValuationDTO(
        as_of=model.as_of,
        passed=model.passed,
        reason=model.reason,
        gamma_annual_per_z=_annual(model.gamma_estimate),
        gamma_used_annual_per_z=_annual(model.gamma),
        sign_probability=model.sign_probability,
        months=model.months,
        companies=model.companies,
        oos_improvement=model.oos_improvement,
        oos_win_share=model.oos_win_share,
        origins=[
            ValuationOriginDTO(
                origin=o.origin,
                mse_model=o.mse_model,
                mse_zero=o.mse_zero,
                observations=o.observations,
            )
            for o in model.origins
        ],
    )


def forecast_lead(ticker: str, forecast: PriceForecast, months: int = LEAD_HORIZON) -> str:
    horizon = next((h for h in forecast.horizons if h.months == months), forecast.horizons[-1])
    return (
        f"Em {horizon.months} meses, há {pct(horizon.up.value)} de chance de {ticker} estar acima "
        f"do preço de hoje ({money(forecast.price_now)}). A faixa de 90% vai de "
        f"{money(horizon.price_at(0.05))} a {money(horizon.price_at(0.95))}."
    )


class ForecastHandler:
    def __init__(
        self,
        uow_factory: UoWFactory,
        portfolio_service: PortfolioApplicationService,
        catalog_top: int = 0,
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service
        self.catalog_top = catalog_top

    def refresh(self, asset_id: int, *, today: date | None = None) -> AssetForecastDTO:
        """Forecast this asset now, from the stored history, and keep following it on demand."""
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if asset is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            as_of = today or date.today()
            cdi, _ipca = stored_macro_rates(uow, self.portfolio_service.gateway, today=as_of)
            projections = current_policy(uow.policies).valuation.projections
            if projections.projected_cdi_rate is not None:
                cdi = projections.projected_cdi_rate
            counts = refresh_forecasts(
                uow,
                cdi_annual=cdi,
                usd_brl=stored_usd_brl(uow, self.portfolio_service.gateway),
                catalog_top=self.catalog_top,
                today=as_of,
                tickers=[asset.ticker],
                on_demand=True,
            )
            if counts["forecasts"] + counts["insufficient"] == 0:
                raise ValidationError(
                    f"Não há preço nem histórico guardado de {asset.ticker} para calcular a "
                    "previsão; carregue o histórico da simulação em Dados de mercado.",
                    code="FORECAST_NO_DATA",
                )
            uow.commit()
        return self.get(asset_id)

    def get(self, asset_id: int) -> AssetForecastDTO:
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if asset is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            stored = uow.forecasts.latest(asset.ticker)
            seal = forecast_seal(uow.forecasts.latest_calibration())
            requested = bool(stored is not None and stored.payload.get("on_demand"))
            base = {
                "asset_id": asset_id,
                "ticker": asset.ticker,
                "seal": _seal_dto(seal),
                "requested": requested,
            }
            if stored is None:
                return AssetForecastDTO(**base, status="NOT_COMPUTED")
            if stored.payload.get("status") != "OK":
                months = stored.payload.get("months", 0)
                needed = REQUESTED_MIN_MONTHS if requested else MIN_HISTORY_MONTHS
                hint = (
                    ""
                    if requested or months < REQUESTED_MIN_MONTHS
                    else f" Com {REQUESTED_MIN_MONTHS} meses ou mais dá para pedir a previsão só "
                    "deste ativo, com aviso de confiança."
                )
                return AssetForecastDTO(
                    **base,
                    status="INSUFFICIENT_HISTORY",
                    as_of=stored.as_of,
                    months_used=months,
                    warnings=[
                        f"São precisos {needed} meses de histórico de preço; "
                        f"{asset.ticker} tem {months}.{hint}"
                    ],
                )
            forecast = PriceForecast.from_dict(stored.payload)
            if seal.level < MIN_SEAL_LEVEL and not requested:
                return AssetForecastDTO(
                    **base,
                    status="LOW_CONFIDENCE",
                    as_of=forecast.as_of,
                    warnings=[
                        "As faixas ainda não se confirmaram bem no passado; a previsão fica "
                        "oculta até a calibração subir para “Use com cautela”."
                    ],
                )
            average = self._average_price(uow, asset.ticker)
            fair = self._fair_value(uow, asset, forecast.price_now)
        cautions = []
        if forecast.months_used < MIN_HISTORY_MONTHS:
            cautions.append(
                f"Histórico curto: {forecast.months_used} meses de {MIN_HISTORY_MONTHS}. A faixa "
                "se apoia mais na classe do que no próprio ativo; leia com cautela."
            )
        if seal.level < MIN_SEAL_LEVEL:
            cautions.append(
                f"A calibração ainda não confirma estas faixas (selo “{seal.label}”); a previsão "
                "aparece porque foi pedida para este ativo."
            )
        return self._dto(base, forecast, average, fair, cautions)

    def quality(self) -> ForecastQualityDTO:
        with self.uow_factory() as uow:
            stored = uow.forecasts.latest_calibration()
            model = uow.forecasts.latest_model(VALUATION)
        valuation = _valuation_dto(ValuationModel.from_dict(model.payload)) if model else None
        if stored is None:
            return ForecastQualityDTO(
                status="NOT_COMPUTED", seal=_seal_dto(forecast_seal(None)), valuation=valuation
            )
        cal = ForecastCalibration.from_dict(stored.payload)
        return ForecastQualityDTO(
            status="OK",
            as_of=cal.as_of,
            horizon_months=cal.horizon_months,
            windows=cal.windows,
            effective_windows=cal.effective_windows,
            assets=cal.assets,
            coverage_50=cal.coverage_50,
            coverage_90=cal.coverage_90,
            mean_pit=cal.mean_pit,
            brier=cal.brier,
            brier_reference=cal.brier_reference,
            first_origin=cal.first_origin,
            last_origin=cal.last_origin,
            seal=_seal_dto(forecast_seal(stored)),
            valuation=valuation,
        )

    # --- internals --------------------------------------------------------------------------

    def _average_price(self, uow: object, ticker: str) -> float | None:
        report = self.portfolio_service.build_portfolio_report(uow)  # type: ignore[arg-type]
        position = next(
            (p for p in report.positions if p.ticker.upper() == ticker.upper() and p.quantity > 0),
            None,
        )
        if position is None or not position.average_price:
            return None
        # The forecast is in reais: a dollar asset's average price goes at today's rate.
        return float(position.average_price) * float(position.fx_rate or 1.0)

    def _fair_value(self, uow: object, asset: object, price: float) -> float | None:
        try:
            fund = stored_fundamentals(uow, self.portfolio_service.gateway, asset)  # type: ignore[arg-type]
            valuation = self.portfolio_service.value(uow, asset, price, fund)  # type: ignore[arg-type]
        except Exception:  # a valuation problem must not hide the forecast
            return None
        return valuation.fair_value if valuation.applicable and valuation.fair_value else None

    @staticmethod
    def _dto(
        base: dict,
        forecast: PriceForecast,
        average: float | None,
        fair: float | None,
        cautions: list[str],
    ) -> AssetForecastDTO:
        horizons = []
        for h in forecast.horizons:
            grid = h.price_quantiles
            thresholds = [
                ForecastThresholdDTO(
                    key="NOW",
                    label="Acima do preço de hoje",
                    price=forecast.price_now,
                    direction="above",
                    probability=h.up.value,
                )
            ]
            if average:
                thresholds.append(
                    ForecastThresholdDTO(
                        key="AVERAGE",
                        label="Acima do seu preço médio",
                        price=round(average, 2),
                        direction="above",
                        probability=chance_above(grid, average),
                    )
                )
            if fair:
                thresholds.append(
                    ForecastThresholdDTO(
                        key="FAIR",
                        label="Acima do preço justo (valuation)",
                        price=round(fair, 2),
                        direction="above",
                        probability=chance_above(grid, fair),
                    )
                )
            thresholds.append(
                ForecastThresholdDTO(
                    key="FALL_20",
                    label=f"Queda de {pct(FALL_THRESHOLD)} ou mais",
                    price=round(forecast.price_now * (1 - FALL_THRESHOLD), 2),
                    direction="below",
                    probability=h.fall_20.value,
                )
            )
            horizons.append(
                ForecastHorizonDTO(
                    months=h.months,
                    target_date=forecast.as_of + timedelta(days=round(h.months * 30.44)),
                    p5=round(h.price_at(0.05), 2),
                    p25=round(h.price_at(0.25), 2),
                    p50=round(h.price_at(0.50), 2),
                    p75=round(h.price_at(0.75), 2),
                    p95=round(h.price_at(0.95), 2),
                    total_return_p50=h.total_return_p50,
                    up=ForecastProbabilityDTO(value=h.up.value, low=h.up.low, high=h.up.high),
                    fall_20=ForecastProbabilityDTO(
                        value=h.fall_20.value, low=h.fall_20.low, high=h.fall_20.high
                    ),
                    thresholds=thresholds,
                    price_quantiles=grid,
                )
            )
        return AssetForecastDTO(
            **base,
            status="OK",
            as_of=forecast.as_of,
            price_now=forecast.price_now,
            lead=forecast_lead(base["ticker"], forecast),
            months_used=forecast.months_used,
            beta=forecast.beta,
            alpha_annual=forecast.alpha_annual,
            shrinkage=forecast.shrinkage,
            dividend_yield_annual=forecast.dividend_yield_annual,
            expected_total_return_annual=forecast.expected_total_return_annual,
            horizons=horizons,
            drivers=[
                ForecastDriverDTO(key=d.key, label=d.label, annual=d.annual, note=d.note)  # type: ignore[arg-type]
                for d in forecast.drivers
            ],
            cautions=cautions,
            warnings=forecast.warnings,
            model_version=forecast.model_version,
        )
