"""Compare two Locust runs (before vs after) from their *_stats.csv files.

Usage: python loadtest/compare.py results/nocache_stats.csv results/cache_stats.csv
"""
import csv
import sys


def load(path):
    rows = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            name = row["Name"] or "Aggregated"
            rows[name] = row
    return rows


def num(row, col):
    try:
        return float(row[col])
    except (KeyError, ValueError, TypeError):
        return float("nan")


def change(before, after, lower_is_better=True):
    if not before or before != before or after != after:
        return "n/a"
    pct = (after - before) / before * 100
    good = pct < 0 if lower_is_better else pct > 0
    return f"{pct:+.0f}% {'better' if good else 'worse'}" if abs(pct) >= 1 else "same"


def main(before_path, after_path):
    a, b = load(before_path), load(after_path)
    metrics = [("Median (ms)", "50%", True), ("p95 (ms)", "95%", True), ("p99 (ms)", "99%", True),
               ("Requests/s", "Requests/s", False), ("Failures", "Failure Count", True)]
    for name in [n for n in b if n in a and not n.startswith("setup")]:
        print(f"\n{name}   (requests: {int(num(a[name], 'Request Count'))} -> {int(num(b[name], 'Request Count'))})")
        print(f"  {'metric':<14}{'before':>10}{'after':>10}   change")
        for label, col, lower in metrics:
            x, y = num(a[name], col), num(b[name], col)
            print(f"  {label:<14}{x:>10.1f}{y:>10.1f}   {change(x, y, lower)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])