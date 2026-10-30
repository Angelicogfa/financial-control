"""Use cases of the price forecasts (Phase 42.1): read what the worker stored.

The screen never computes: it reads the latest forecast of the asset and the latest
calibration, adds the prices that matter to the user (today's, the average paid, the fair
value) and hides the forecast while its confidence is below "Use com cautela" (decision 42.0-5).
"""

from __future__ import annotations

from datetime import timedelta

from controllers.assets.responses import (
    AssetForecastDTO,
    ForecastDriverDTO,
    ForecastHorizonDTO,
    ForecastProbabilityDTO,
    ForecastQualityDTO,
    ForecastSealDTO,
    ForecastThresholdDTO,
)
from controllers.shared.dependencies import UoWFactory
from core.errors import NotFoundError
from domain.forecast.calibration import ForecastCalibration
from domain.forecast.model import FALL_THRESHOLD, PriceForecast, chance_above
from domain.forecast.repositories import StoredCalibration
from domain.portfolio.services.service import PortfolioApplicationService
from domain.simulation.studies import Seal, confidence_seal, money, pct
from infra.providers.stored import stored_fundamentals

MIN_SEAL_LEVEL = 2  # "Use com cautela" or better (decision 42.0-5)
LEAD_HORIZON = 12


def forecast_seal(stored: StoredCalibration | None) -> Seal:
    if stored is None:
        return confidence_seal(None, 0.0, None, None)
    cal = ForecastCalibration.from_dict(stored.payload)
    return confidence_seal(cal.coverage_90, cal.effective_windows, None, cal.as_of)


def _seal_dto(seal: Seal) -> ForecastSealDTO:
    return ForecastSealDTO(level=seal.level, label=seal.label, text=seal.text)


def forecast_lead(ticker: str, forecast: PriceForecast, months: int = LEAD_HORIZON) -> str:
    horizon = next((h for h in forecast.horizons if h.months == months), forecast.horizons[-1])
    return (
        f"Em {horizon.months} meses, há {pct(horizon.up.value)} de chance de {ticker} estar acima "
        f"do preço de hoje ({money(forecast.price_now)}). A faixa de 90% vai de "
        f"{money(horizon.price_at(0.05))} a {money(horizon.price_at(0.95))}."
    )


class ForecastHandler:
    def __init__(
        self, uow_factory: UoWFactory, portfolio_service: PortfolioApplicationService
    ) -> None:
        self.uow_factory = uow_factory
        self.portfolio_service = portfolio_service

    def get(self, asset_id: int) -> AssetForecastDTO:
        with self.uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if asset is None:
                raise NotFoundError(f"Asset id={asset_id} not found")
            stored = uow.forecasts.latest(asset.ticker)
            seal = forecast_seal(uow.forecasts.latest_calibration())
            base = {"asset_id": asset_id, "ticker": asset.ticker, "seal": _seal_dto(seal)}
            if stored is None:
                return AssetForecastDTO(**base, status="NOT_COMPUTED")
            if stored.payload.get("status") != "OK":
                months = stored.payload.get("months", 0)
                return AssetForecastDTO(
                    **base,
                    status="INSUFFICIENT_HISTORY",
                    as_of=stored.as_of,
                    months_used=months,
                    warnings=[
                        f"São precisos 36 meses de histórico de preço; {asset.ticker} tem {months}."
                    ],
                )
            forecast = PriceForecast.from_dict(stored.payload)
            if seal.level < MIN_SEAL_LEVEL:
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
        return self._dto(base, forecast, average, fair)

    def quality(self) -> ForecastQualityDTO:
        with self.uow_factory() as uow:
            stored = uow.forecasts.latest_calibration()
        if stored is None:
            return ForecastQualityDTO(status="NOT_COMPUTED", seal=_seal_dto(forecast_seal(None)))
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
        base: dict, forecast: PriceForecast, average: float | None, fair: float | None
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
            warnings=forecast.warnings,
            model_version=forecast.model_version,
        )
