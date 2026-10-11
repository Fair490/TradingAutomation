"""
Central configuration for the Market Health Dashboard.

Everything that a user might reasonably want to tweak (tickers, windows,
thresholds, file locations) lives here so the rest of the code stays generic.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "market.duckdb"

# The user drops the current Nifty Total Market constituents here.
# Expected columns (NSE's standard export): Company Name, Industry, Symbol,
# Series, ISIN Code.  An optional "Yahoo Ticker" column overrides the default
# "<SYMBOL>.NS" mapping for symbols that differ on Yahoo Finance.
UNIVERSE_FILE = DATA_DIR / "universe.csv"
UNIVERSE_SYMBOL_COLUMNS = ("Symbol", "SYMBOL", "symbol", "Ticker")
UNIVERSE_NAME_COLUMNS = ("Company Name", "COMPANY NAME", "Name", "company_name")
UNIVERSE_OVERRIDE_COLUMNS = ("Yahoo Ticker", "yahoo_ticker", "Override", "YahooTicker")
YF_SUFFIX = ".NS"
# NSE "Series" codes kept from the universe file (EQ/BE equities, RR = REITs &
# InvITs which are part of the Nifty Total Market index).
UNIVERSE_SERIES_KEEP = {"EQ", "BE", "BZ", "SM", "ST", "RR"}

# --------------------------------------------------------------------------- #
# History windows
# --------------------------------------------------------------------------- #
# Charts show 5 years.  The 200DMA needs ~200 trading days of warm-up before
# the first charted day, so stocks are downloaded from ~14 months earlier.
HISTORY_YEARS = 5
MA_WARMUP_MONTHS = 14
MA_WINDOW = 200

# --------------------------------------------------------------------------- #
# Index line used as the grey overlay on the breadth / A-D panels
# --------------------------------------------------------------------------- #
# Tried in order; the first ticker that actually returns data from Yahoo wins
# and its *display name* is what appears in the chart legend.
INDEX_CANDIDATES: list[tuple[str, str]] = [
    ("Nifty Total Market", "^CNXTOTAL"),  # best-effort; often unavailable on Yahoo
    ("Nifty 500", "^CRSLDX"),  # documented fallback
]

# --------------------------------------------------------------------------- #
# Non-stock series
# --------------------------------------------------------------------------- #
# kind -> list of (display name, yfinance ticker)
GLOBAL_INDICES: list[tuple[str, str]] = [
    ("Dow Jones", "^DJI"),
    ("Nasdaq", "^IXIC"),
    ("Nikkei 225", "^N225"),
    ("KOSPI", "^KS11"),
    ("Hang Seng", "^HSI"),
    ("S&P 500", "^GSPC"),
    ("India VIX", "^INDIAVIX"),
]

# Display unit for each global / macro / commodity series (shown on the card
# footer). "price" is the default and does not need to be listed explicitly.
GLOBAL_UNITS: dict[str, str] = {
    "INR=X": "₹ per $",
    "^TNX": "bps",
    "GC=F": "USD/oz",
    "SI=F": "USD/oz",
    "BZ=F": "USD/bbl",
    "^INDIAVIX": "index",
}

MACRO_SERIES: list[tuple[str, str]] = [
    ("USD/INR", "INR=X"),  # rupees per dollar: rising line = weaker rupee
    ("Dollar Index", "DX-Y.NYB"),
    ("US 10-Year Yield", "^TNX"),
]

# --------------------------------------------------------------------------- #
# Sector / thematic / broad-market ETFs
# --------------------------------------------------------------------------- #
# (NSE symbol, display label, group).  The symbol is mapped to Yahoo the same
# way as stocks: "<SYMBOL>.NS".  Edit this list to add or remove ETFs - the
# dashboard, the downloader and the comparison chart all read it from here.
# Groups drive the filter chips in the UI.
ETF_SERIES: list[tuple[str, str, str]] = [
    # Banking & financials
    ("BANKBEES", "Nifty Bank", "Banking"),
    ("PSUBNKBEES", "Nifty PSU Bank", "Banking"),
    ("PVTBANIETF", "Nifty Private Bank", "Banking"),
    # Sectors
    ("ITBEES", "Nifty IT", "Sector"),
    ("PHARMABEES", "Nifty Pharma", "Sector"),
    ("AUTOBEES", "Nifty Auto", "Sector"),
    ("FMCGIETF", "Nifty FMCG", "Sector"),
    ("METALIETF", "Nifty Metal", "Sector"),
    ("OILIETF", "Nifty Oil & Gas", "Sector"),
    ("GROWWPOWER", "Nifty Power", "Sector"),
    ("INFRABEES", "Nifty Infrastructure", "Sector"),
    ("MOREALTY", "Nifty Realty", "Sector"),
    ("CONSUMBEES", "Nifty India Consumption", "Sector"),
    # Themes
    ("MAKEINDIA", "Nifty India Manufacturing", "Theme"),
    ("MODEFENCE", "Nifty India Defence", "Theme"),
    ("GROWWEV", "Nifty EV & New Age Auto", "Theme"),
    ("TNIDETF", "Nifty India Digital", "Theme"),
    ("MNC", "Nifty MNC", "Theme"),
    ("CPSEETF", "Nifty CPSE", "Theme"),
    ("ICICIB22", "S&P BSE Bharat 22", "Theme"),
    # Broad market
    ("NIFTYBEES", "Nifty 50", "Broad market"),
    ("JUNIORBEES", "Nifty Next 50", "Broad market"),
    ("MIDCAPETF", "Nifty Midcap 150", "Broad market"),
    ("HDFCSML250", "Nifty Smallcap 250", "Broad market"),
    # International
    ("MON100", "Nasdaq 100", "International"),
    ("HNGSNGBEES", "Hang Seng", "International"),
    # Commodities
    ("GOLDBEES", "Gold", "Commodity"),
    ("SILVERBEES", "Silver", "Commodity"),
]

# How many points a single ETF line is thinned to before leaving the API.
ETF_SPARK_POINTS = 70
ETF_CHART_POINTS = 420

# Periods the ETF ranking selector supports. The frontend sorts by relative
# performance over the chosen period; the "since listing" note is shown when
# an ETF's first available date is inside the selected window.
ETF_RANK_PERIODS: tuple[str, ...] = ("1M", "3M", "6M", "1Y")

# Moving-average windows offered as overlays on price charts (ETF, global,
# macro, commodities). Computed server-side and shipped as extra series.
MA_WINDOWS: tuple[int, ...] = (50, 150)

# --------------------------------------------------------------------------- #
# RS (Relative Strength) benchmarks
# --------------------------------------------------------------------------- #
# The RS indicator compares any series' close to one of these benchmarks. The
# frontend shows a 3-way switcher in the TopBar and an RS sub-chart under
# every price chart when the RS toggle is on.
RS_BENCHMARKS: list[tuple[str, str]] = [
    ("Nifty 500", "^CRSLDX"),   # the default, also used for the breadth overlay
    ("Nifty 50", "^NSEI"),
    ("Bank Nifty", "^NSEBANK"),
]
RS_SMA_WINDOW = 30  # Pine-script default, unused if RS SMA isn't plotted

COMMODITIES: list[tuple[str, str]] = [
    ("Gold", "GC=F"),
    ("Silver", "SI=F"),
    ("Brent Crude (UK Oil)", "BZ=F"),
]

# Series where a holiday gap may be forward-filled for display purposes.
# Stock prices are NEVER forward-filled.
FORWARD_FILL_KINDS = {"macro", "commodity"}

# --------------------------------------------------------------------------- #
# Breadth thresholds and chart defaults
# --------------------------------------------------------------------------- #
BREADTH_OVERBOUGHT = 80.0
BREADTH_MIDLINE = 50.0
BREADTH_OVERSOLD = 20.0

AD_SMOOTHING_WINDOW = 10

DATE_RANGES: dict[str, int | None] = {
    "1M": 30,
    "3M": 91,
    "6M": 182,
    "1Y": 365,
    "3Y": 365 * 3,
    "5Y": 365 * 5,
}
DEFAULT_RANGE = "5Y"

# --------------------------------------------------------------------------- #
# Download behaviour
# --------------------------------------------------------------------------- #
BATCH_SIZE = 50
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0  # doubled on each retry
REQUEST_PAUSE_SECONDS = 0.6  # small pause between batches, keeps Yahoo happy

# --------------------------------------------------------------------------- #
# Colours (kept consistent across every panel)
# --------------------------------------------------------------------------- #
COLOR_INDEX = "#9aa0a6"  # the Nifty overlay is always grey
COLOR_AD = "#2f6fdb"
COLOR_BREADTH = "#1a9b6c"
COLOR_UP = "#1a9b6c"
COLOR_DOWN = "#d8453c"
COLOR_MACRO = ["#2f6fdb", "#9b5de5", "#e07b39"]
COLOR_COMMODITY = ["#c9a227", "#8c9196", "#3f7d58"]
COLOR_GRID = "#e9ecef"

FOOTNOTE_SURVIVORSHIP = (
    "Based on current constituents; survivorship bias applies."
)
