import argparse
import csv


def safe_div(a, b):
    return a / b if b else 0.0


def evaluate(path):
    labelled = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            label = str(row.get("human_label", "")).strip()
            if label not in {"0", "1"}:
                continue
            labelled.append((int(row["predicted_relevant"]), int(label)))

    if not labelled:
        raise RuntimeError("No labelled rows found. Fill human_label with 1 or 0 first.")

    tp = sum(p == 1 and y == 1 for p, y in labelled)
    fp = sum(p == 1 and y == 0 for p, y in labelled)
    tn = sum(p == 0 and y == 0 for p, y in labelled)
    fn = sum(p == 0 and y == 1 for p, y in labelled)

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    accuracy = safe_div(tp + tn, len(labelled))

    print(f"Labelled articles: {len(labelled)}")
    print(f"TP={tp}  FP={fp}  TN={tn}  FN={fn}")
    print(f"Precision: {precision:.1%}")
    print(f"Recall:    {recall:.1%}")
    print(f"F1:        {f1:.1%}")
    print(f"Accuracy:  {accuracy:.1%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("labels", nargs="?", default="evaluation/labels.csv")
    args = parser.parse_args()
    evaluate(args.labels)
