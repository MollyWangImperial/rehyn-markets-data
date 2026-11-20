"""Runs a spread of real questions through the engine. Exits non-zero if any question crashes or comes back empty."""
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "server"))
import engine  # noqa: E402

QUESTIONS = [
    "Apple share price since 2020", "AAPL", "Compare gold and bitcoin since 2020", "Compare NVDA, AMD and INTC over the last 3 years",
    "What did Brent do after OPEC decisions?", "Fed cuts of 50bp and the S&P 500", "What happened to gold after invasions?", "How do airlines react after a Fed rate hike?",
    "After VIX spikes above 40 how did the S&P 500 do?", "Nvidia revenue", "Microsoft net income by quarter", "Tesla free cash flow", "Latest 8-K filings for JPMorgan",
    "Insider selling at Tesla", "Apple dividends", "What happened on 16 March 2020?", "2008-09-15", "Tesla price on 2 January 2024", "US CPI", "inflation since 2015", "unemployment rate",
    "10 year yield", "US yield curve", "Yield curve in 2019", "Geopolitical risk index", "Geopolitical risk Taiwan", "CAPE ratio", "Inflation in Turkey", "GDP of Brazil",
    "Speculator positioning in gold", "Who is net short?  positioning", "Short volume for Tesla", "Options on Apple", "Public attention for recession", "Attention on Nvidia",
    "Odds of a recession", "Sanctions on Rosneft", "OFAC sanctions", "Conflict deaths in Ukraine", "FOMC statement in December 2008", "Executive orders on tariffs",
    "News about OPEC", "Latest headlines", "Taiwan news since 2022", "Worst days for the S&P 500", "Best day for Nvidia", "Best performing energy stocks this year", "Top crypto this month",
    "Which data needs a licence?", "What datasets do you have?", "SELECT symbol, name FROM ref_asset WHERE sector='Energy' LIMIT 5", "Volatility of the Nasdaq since 2022", "semiconductor export controls",
    "fed funds rate", "Bank of England", "copper", "Rolls-Royce", "Berkshire Hathaway revenue", "Vodafone",
    "Berkshire Hathaway holdings", "Who owns Nvidia?", "13F", "What did the S&P 500 do in 2008?", "Bitcoin", "Federal Reserve", "Apple vs Microsoft",
]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    bad = 0
    for q in QUESTIONS:
        try:
            a = engine.ask(q)
            kinds = ",".join(b["type"] for b in a["blocks"])
            lede = next((b["text"] for b in a["blocks"] if b["type"] == "lede"), "")
            empty = len(a["blocks"]) == 1 and ("Nothing" in lede or "No " == lede[:3])
            print(f"{'EMPTY' if empty else 'ok   '} {q[:44]:<44} [{kinds[:36]}] {lede[:120]}")
            bad += empty
        except Exception:
            bad += 1
            print(f"CRASH {q}")
            traceback.print_exc(limit=3)
    print(f"{len(QUESTIONS)} questions, {bad} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
