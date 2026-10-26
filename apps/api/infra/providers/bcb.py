"""Central Bank of Brazil (BCB SGS) provider for CDI (12), SELIC (11), and IPCA (433)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import httpx

from core.helpers.units import BCB_SERIES_UNITS, rate_fraction
from domain.shared.entities import MarketSeriesPoint

BCB_SERIES_CDI_DAILY = 12
BCB_SERIES_SELIC_DAILY = 11
BCB_SERIES_IPCA_MONTHLY = 433

# BCB SGS rejects daily-series requests spanning more than 10 years.
MAX_WINDOW_DAYS = 3650

SYMBOL_TO_SERIES_CODE: dict[str, int] = {
    "CDI": BCB_SERIES_CDI_DAILY,
    "SELIC": BCB_SERIES_SELIC_DAILY,
    "IPCA": BCB_SERIES_IPCA_MONTHLY,
}


class BcbSgsProvider:
    """HTTP client for Banco Central do Brasil SGS time series API."""

    def __init__(
        self,
        base_url: str = "https://api.bcb.gov.br/dados/serie",
        default_cdi_annual: float = 0.1075,
        default_ipca_annual: float = 0.045,
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_cdi_annual = default_cdi_annual
        self.default_ipca_annual = default_ipca_annual
        self._client = client or httpx.Client(timeout=timeout)

    def fetch_series(
        self,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MarketSeriesPoint]:
        """Fetch BCB SGS series points for 'CDI', 'SELIC', or 'IPCA'."""
        norm_symbol = symbol.strip().upper()
        series_code = SYMBOL_TO_SERIES_CODE.get(norm_symbol)
        if series_code is None:
            raise ValueError(f"Unsupported BCB series symbol: {symbol}")

        end = end_date or date.today()
        start = start_date or (end - timedelta(days=365))
        points: list[MarketSeriesPoint] = []
        window_start = start
        while window_start <= end:
            window_end = min(end, window_start + timedelta(days=MAX_WINDOW_DAYS - 1))
            points.extend(self._fetch_window(norm_symbol, series_code, window_start, window_end))
            window_start = window_end + timedelta(days=1)
        points.sort(key=lambda p: p.reference_date)
        return points

    def _fetch_window(
        self, symbol: str, series_code: int, start: date, end: date
    ) -> list[MarketSeriesPoint]:
        url = f"{self.base_url}/bcdata.sgs.{series_code}/dados"
        params = {
            "formato": "json",
            "dataInicial": start.strftime("%d/%m/%Y"),
            "dataFinal": end.strftime("%d/%m/%Y"),
        }
        try:
            resp = self._client.get(url, params=params)
            resp.raise_for_status()
            rows = resp.json()
        except Exception:
            return []

        if not isinstance(rows, list):
            return []

        points: list[MarketSeriesPoint] = []
        for row in rows:
            raw_date = row.get("data")
            raw_val = row.get("valor")
            if not raw_date or raw_val is None:
                continue
            try:
                pt_date = datetime.strptime(str(raw_date), "%d/%m/%Y").date()
                val = float(str(raw_val).replace(",", "."))
                points.append(
                    MarketSeriesPoint(
                        symbol=symbol,
                        reference_date=pt_date,
                        value=val,
                        unit=BCB_SERIES_UNITS[symbol],
                    )
                )
            except ValueError:
                continue
        return points

    def get_annualized_cdi_rate(self) -> float:
        """Compute annualized CDI rate from the latest daily BCB SGS 12 entry, or fallback."""
        today = date.today()
        pts = self.fetch_series("CDI", start_date=today - timedelta(days=30), end_date=today)
        if not pts:
            return self.default_cdi_annual
        daily_frac = rate_fraction(pts[-1].value, pts[-1].unit)
        annual = (1.0 + daily_frac) ** 252.0 - 1.0
        return round(annual, 6)

    def get_annualized_ipca_rate(self) -> float:
        """Compute trailing 12-month IPCA rate from BCB SGS 433 monthly percentages, or fallback."""
        today = date.today()
        pts = self.fetch_series("IPCA", start_date=today - timedelta(days=400), end_date=today)
        if not pts:
            return self.default_ipca_annual
        last_12 = pts[-12:]
        factor = 1.0
        for p in last_12:
            factor *= 1.0 + rate_fraction(p.value, p.unit)
        if len(last_12) < 12 and len(last_12) > 0:
            factor = factor ** (12.0 / len(last_12))
        return round(factor - 1.0, 6)
