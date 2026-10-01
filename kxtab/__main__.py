"""CLI: python -m kxtab [--ticker T] [--table history|orderbook|trades] [--csv out.csv]"""
from __future__ import annotations

import argparse
import json
import time

import pandas as pd

from . import history, orderbook, trades

TABLES = {"history": history, "orderbook": orderbook, "trades": trades}


def main() -> None:
    parser = argparse.ArgumentParser(prog="kxtab", description="Preview a KX-Tab table without Tableau.")
    parser.add_argument("--ticker", help="overrides KXTAB_TICKER")
    parser.add_argument("--table", choices=TABLES, default="history")
    parser.add_argument("--csv", help="write the table to this CSV file")
    args = parser.parse_args()

    start = time.perf_counter()
    cols = TABLES[args.table](args.ticker)
    secs = time.perf_counter() - start
    df = pd.DataFrame(cols)
    size_mb = len(json.dumps(cols)) / 1e6
    print(f"{args.table}: {len(df):,} rows x {len(df.columns)} columns in {secs:.1f}s (~{size_mb:.1f} MB to Tableau)")
    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"wrote {args.csv}")
    else:
        with pd.option_context("display.width", 200, "display.max_columns", 12):
            print(df.head(10))


if __name__ == "__main__":
    main()
