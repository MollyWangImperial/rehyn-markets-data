"""Run ingest steps by name: python -I ingest/run.py reference prices

Run with -I because source files are untrusted input. -I drops the script folder from
sys.path, so it is put back here, pointing only at this project's own code.
"""
import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from core import DB_PATH, init_db  # noqa: E402

STEPS = {
    "reference": ("s_reference", "run"),
    "prices": ("s_prices", "yahoo"),
    "prices_missing": ("s_prices", "yahoo_missing"),
    "eia": ("s_series", "eia"),
    "crypto": ("s_prices", "coinbase"),
    "series": ("s_series", "run"),
    "companies": ("s_companies", "run"),
    "news": ("s_news", "run"),
    "gdelt": ("s_news", "gdelt"),
    "news_sentiment": ("sentiment_job", "collector"),
    "federal_register": ("s_news", "federal_register"),
    "positioning": ("s_positioning", "run"),
    "geo": ("s_geo", "run"),
    "short": ("s_positioning", "short_volume"),
    "attention": ("s_positioning", "pageviews"),
    "open": ("s_open", "run"),
    "bls": ("s_open", "bls"),
    "holdings": ("s_open", "holdings"),
    "primary": ("s_primary", "run"),
    "world": ("s_world", "run"),
    "fed_fx": ("s_world", "fed_fx"),
    "fed_rates": ("s_world", "fed_rates"),
    "quakes": ("s_world", "earthquakes"),
    "enso": ("s_world", "enso"),
    "worldbank": ("s_world", "world_bank"),
    "wgi": ("s_world", "governance"),
    "sec_tickers": ("s_world", "sec_tickers"),
    "tic": ("s_world", "tic"),
    "chokepoints": ("s_world", "chokepoints"),
    "eia_world": ("s_world", "eia_world"),
    "crops": ("s_world", "crops"),
    "gscpi": ("s_world", "supply_chain"),
    "sanctions_un": ("s_world", "sanctions_un"),
    "sanctions_uk": ("s_world", "sanctions_uk"),
    "sanctions_eu": ("s_world", "sanctions_eu"),
    "names": ("s_derived", "clean_names"),
    "derived": ("s_derived", "run"),
    "verify": ("verify", "run"),
    "catalogue": ("catalogue", "refresh"),
}


def main(names):
    con = init_db()
    for name in names:
        mod, fn = STEPS[name]
        try:
            getattr(importlib.import_module(mod), fn)(con)
        except Exception as e:
            print(f"[{name}] FAILED: {type(e).__name__}: {e}", flush=True)
    size = DB_PATH.stat().st_size / 1e9
    print(f"database size {size:.2f} GB", flush=True)
    if size > 5:
        print("WARNING: past the agreed 5 GB limit, stop and check with the user", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or list(STEPS))
