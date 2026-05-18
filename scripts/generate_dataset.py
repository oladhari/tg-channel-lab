#!/usr/bin/env python3
"""
generate_dataset.py — Export historical token calls + 5-minute outcomes to CSV.

Reads directly from the existing DB (calls + price_points tables).
No live listening. No Telegram. Just SQL → CSV.

Usage:
    python scripts/generate_dataset.py
    python scripts/generate_dataset.py --output my_data.csv --status DONE
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent

SQL = """
COPY (
  SELECT
    c.mint,
    ch.telegram_username                                          AS channel,
    c.started_at                                                  AS called_at,
    c.entry_price_usd                                             AS entry_price,
    c.market_cap                                                  AS entry_mcap,
    ROUND((MAX(pp.price_usd) / NULLIF(c.entry_price_usd, 0))::numeric, 4)
                                                                  AS peak_multiplier,
    (MAX(pp.price_usd) / NULLIF(c.entry_price_usd, 0) >= 1.35)   AS hit_tp35,
    (MAX(pp.price_usd) / NULLIF(c.entry_price_usd, 0) >= 1.50)   AS hit_tp50,
    (MIN(pp.price_usd) <= c.entry_price_usd * 0.80)               AS hit_sl20,
    (SELECT pp2.t_sec
       FROM price_points pp2
      WHERE pp2.call_id = c.id
      ORDER BY pp2.price_usd DESC
      LIMIT 1)                                                     AS time_to_peak_sec
  FROM calls c
  JOIN channels ch ON c.channel_id = ch.id
  LEFT JOIN price_points pp ON pp.call_id = c.id
  WHERE c.entry_price_usd IS NOT NULL
    AND c.entry_price_usd > 0
    {status_filter}
  GROUP BY c.id, ch.telegram_username
  ORDER BY c.started_at
) TO STDOUT WITH CSV HEADER
"""


def _get_container_id() -> str:
    result = subprocess.run(
        ["docker", "compose", "ps", "-q", "db"],
        capture_output=True, text=True,
        cwd=str(_project_root),
    )
    cid = result.stdout.strip()
    if not cid:
        sys.exit("[ERROR] Docker db container is not running. Start it with: docker compose up -d db")
    return cid


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export historical token calls + outcomes to CSV"
    )
    parser.add_argument("--output", "-o", default="dataset.csv",
                        help="Output CSV file (default: dataset.csv)")
    parser.add_argument("--status", "-s", default="DONE",
                        choices=["DONE", "ALL"],
                        help="DONE = only finished calls (default), ALL = include active/ignored")
    args = parser.parse_args()

    status_filter = "AND c.status = 'DONE'" if args.status == "DONE" else ""
    sql = SQL.format(status_filter=status_filter).strip()

    print(f"[DATASET] Querying DB (status={args.status}) ...", flush=True)
    container_id = _get_container_id()

    import os
    db_name = os.getenv("POSTGRES_DB", "tg_lab")
    db_user = os.getenv("POSTGRES_USER", "tg_lab")

    # Load .env manually if needed
    env_file = _project_root / ".env"
    if env_file.exists() and not os.getenv("POSTGRES_DB"):
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k in ("POSTGRES_DB", "POSTGRES_USER") and k not in os.environ:
                    os.environ[k] = v
        db_name = os.getenv("POSTGRES_DB", "tg_lab")
        db_user = os.getenv("POSTGRES_USER", "tg_lab")

    result = subprocess.run(
        ["docker", "exec", container_id,
         "psql", "-U", db_user, "-d", db_name, "-c", sql],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        sys.exit(f"[ERROR] psql failed:\n{result.stderr.strip()}")

    output = Path(args.output)
    output.write_text(result.stdout)

    lines = result.stdout.strip().splitlines()
    row_count = len(lines) - 1  # subtract header
    print(f"[DATASET] Done. {row_count} rows written to {output}", flush=True)


if __name__ == "__main__":
    main()
