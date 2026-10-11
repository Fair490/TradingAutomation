"""
Reads the stock universe file (current Nifty Total Market constituents) and
maps each NSE symbol to its yfinance ticker.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from backend import config


@dataclass(frozen=True)
class Constituent:
    symbol: str  # NSE symbol, e.g. "RELIANCE"
    ticker: str  # yfinance ticker, e.g. "RELIANCE.NS"
    name: str  # company name
    industry: str = ""


def _first_present(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for col in candidates:
        if col in frame.columns:
            return col
    # case-insensitive second pass
    lowered = {c.lower().strip(): c for c in frame.columns}
    for col in candidates:
        if col.lower() in lowered:
            return lowered[col.lower()]
    return None


def to_yahoo_ticker(symbol: str) -> str:
    """NSE symbol -> yfinance ticker.  '&' and spaces are not valid on Yahoo."""
    clean = str(symbol).strip().upper().replace(" ", "")
    if clean.endswith(config.YF_SUFFIX):
        return clean
    return f"{clean}{config.YF_SUFFIX}"


def load_universe(path: Path | None = None) -> list[Constituent]:
    """
    Load the universe file.  Raises FileNotFoundError with a helpful message
    when the user has not supplied one yet.
    """
    path = Path(path or config.UNIVERSE_FILE)
    if not path.exists():
        raise FileNotFoundError(
            f"Universe file not found at {path}. Save the current Nifty Total "
            "Market constituents there (CSV with a 'Symbol' column)."
        )

    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
    else:
        frame = pd.read_csv(path)

    frame.columns = [str(c).strip() for c in frame.columns]

    symbol_col = _first_present(frame, config.UNIVERSE_SYMBOL_COLUMNS)
    if symbol_col is None and len(frame.columns) == 1:
        # A bare one-column list of symbols is accepted too.
        symbol_col = frame.columns[0]
    if symbol_col is None:
        raise ValueError(
            f"{path.name} has no symbol column. Expected one of: "
            f"{', '.join(config.UNIVERSE_SYMBOL_COLUMNS)}"
        )
    name_col = _first_present(frame, config.UNIVERSE_NAME_COLUMNS)
    override_col = _first_present(frame, config.UNIVERSE_OVERRIDE_COLUMNS)
    industry_col = _first_present(frame, ("Industry", "industry", "Sector"))

    # Equity series only when the column exists (NSE exports use EQ / BE).
    series_col = _first_present(frame, ("Series", "SERIES", "series"))
    if series_col is not None:
        keep = frame[series_col].astype(str).str.strip().str.upper()
        frame = frame[keep.isin(config.UNIVERSE_SERIES_KEEP)]

    out: list[Constituent] = []
    seen: set[str] = set()
    for _, row in frame.iterrows():
        symbol = str(row[symbol_col]).strip().upper()
        if not symbol or symbol in {"NAN", "NONE"}:
            continue
        override = ""
        if override_col is not None and pd.notna(row.get(override_col)):
            override = str(row[override_col]).strip()
        ticker = override or to_yahoo_ticker(symbol)
        if ticker in seen:
            continue
        seen.add(ticker)
        out.append(
            Constituent(
                symbol=symbol,
                ticker=ticker,
                name=str(row[name_col]).strip() if name_col else symbol,
                industry=str(row[industry_col]).strip() if industry_col else "",
            )
        )
    if not out:
        raise ValueError(f"No usable rows found in {path.name}.")
    return out
