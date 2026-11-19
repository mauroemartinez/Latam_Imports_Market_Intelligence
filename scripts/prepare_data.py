"""Turn the Softrade exports into the files under data/raw.

Softrade delivers one Excel workbook per query (country, report, period). Each country has its own
layout, and some layouts change from one year to the next. This script does not harmonize anything:
it keeps the rows and the original column names, and only

  * keeps the columns listed for that country in data/reference/column_map.csv, which are the ones
    the Power BI model reads (addresses, e-mails, phone numbers and tax ids are left out);
  * writes one UTF-8 CSV per country and year, with ISO dates.

The harmonization itself (one schema for the ten countries) happens in Power Query.

Usage:
    python scripts/prepare_data.py <folder with the Softrade .xlsx exports> [data]
"""
import csv
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)  # openpyxl: the exports carry no default style

NAME = re.compile(r"^(?P<cc>[a-z]{2})_(?P<report>[A-Za-z]+)_(?P<year>\d{4})-(?P<m1>\d{2})_\d{4}-(?P<m2>\d{2})\.xlsx$")


def main():
    exports = Path(sys.argv[1])
    data = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "data"
    raw = data / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    wanted = defaultdict(list)           # country -> source columns the model reads
    date_columns = defaultdict(set)
    with open(data / "reference" / "column_map.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            wanted[row["country"]].append(row["source_column"])
            if row["field"] == "Data":
                date_columns[row["country"]].add(row["source_column"])

    groups = defaultdict(list)           # (country, report, year) -> monthly or yearly exports
    for path in sorted(exports.glob("*.xlsx")):
        m = NAME.match(path.name)
        if not m:
            print(f"skipped (unexpected name): {path.name}")
            continue
        groups[m["cc"], m["report"], m["year"]].append(path)

    for old in raw.glob("*.csv"):
        old.unlink()
    total = 0
    for (cc, report, year), paths in sorted(groups.items()):
        if cc not in wanted:
            print(f"skipped (no column map for {cc}): {[p.name for p in paths]}")
            continue
        frames = [pd.read_excel(p, sheet_name=0, dtype=str) for p in paths]
        df = pd.concat(frames, ignore_index=True)
        keep = [c for c in df.columns if c in wanted[cc]]
        missing_fields = sorted(set(wanted[cc]) - set(df.columns))
        df = df[keep].copy()
        for c in date_columns[cc] & set(keep):
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d")
        out = raw / f"{cc}_{report}_{year}.csv"
        df.to_csv(out, index=False, encoding="utf-8", lineterminator="\n")
        total += len(df)
        print(f"{out.name}: {len(df):>6} rows, {len(keep)} columns" + (f"  (not in this layout: {missing_fields})" if missing_fields else ""))
    print(f"{total} rows in {len(list(raw.glob('*.csv')))} files")


if __name__ == "__main__":
    main()
