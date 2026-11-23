#!/usr/bin/env python3
"""Run classify.py logic on data/labeled_sample.jsonl; print accuracy, confusion matrix, mismatches."""
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import classify  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "labeled_sample.jsonl")
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    confusion, bad = Counter(), []
    for r in rows:
        pred = classify.classify_call(r)
        confusion[(r["label"], pred)] += 1
        if pred != r["label"]:
            bad.append((r["call_id"], r["label"], pred, r.get("note", "")))
    ok = len(rows) - len(bad)
    print("accuracy: %d/%d (%.1f%%)" % (ok, len(rows), 100.0 * ok / max(len(rows), 1)))
    labels = classify.LABELS
    print("\nconfusion matrix (rows = truth, cols = predicted):")
    print("%-24s" % "" + "".join("%6s" % l[:5] for l in labels))
    for t in labels:
        if any(confusion[(t, p)] for p in labels):
            print("%-24s" % t + "".join("%6d" % confusion[(t, p)] for p in labels))
    if bad:
        print("\nmismatches:")
        for cid, truth, pred, note in bad:
            print("  %s truth=%s pred=%s %s" % (cid, truth, pred, note))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
