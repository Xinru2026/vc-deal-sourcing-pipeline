import argparse
import csv
import random

from config import DB_PATH
from database import connect, latest_run_id


def export_sample(output_path, sample_size, run_id=None, seed=42):
    conn = connect(DB_PATH)
    try:
        run_id = run_id or latest_run_id(conn)
        if run_id is None:
            raise RuntimeError("No completed run found in the database")
        rows = conn.execute(
            """SELECT a.article_id, a.title, a.source, a.url,
                      CASE WHEN EXISTS (
                        SELECT 1 FROM companies c WHERE c.article_id=a.article_id
                      ) THEN 1 ELSE 0 END AS predicted_relevant
               FROM articles a
               WHERE a.run_id=?
               ORDER BY a.article_index""",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()

    rows = [dict(row) for row in rows]
    random.Random(seed).shuffle(rows)
    rows = rows[:sample_size]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["article_id", "title", "source", "url", "predicted_relevant", "human_label"],
        )
        writer.writeheader()
        for row in rows:
            row["human_label"] = ""
            writer.writerow(row)

    print(f"Exported {len(rows)} rows to {output_path}. Fill human_label with 1 or 0.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evaluation/labels.csv")
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    export_sample(args.output, args.sample_size, args.run_id, args.seed)
