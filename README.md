# Búrková noc — solution

> **Branches.** `master` contains only what the assignment requires: `classify.py`, `predictions_night1.csv`, `TASKS_02-04.md` (tasks 2–4), `NOTES.md` and the scripts that reproduce the numbers. `full` contains the same plus everything else: analysis docs, specification, decision log, tests and helper scripts.

**Removed on purpose.** I removed the assignment text and the call data you provided from this repository, including its git history, because the assignment is not meant to be shared. The readable transcript dumps on `full` are not committed either; regenerate them locally with `python scripts/render_labeled.py` and `python scripts/render_calls.py data/transcripts.jsonl --filter address_rejected --out docs/calls_address_rejected.md`.

To run anything, put the assignment's `data/` folder (`transcripts.jsonl`, `labeled_sample.jsonl`, `calls.csv`, `oms_api_metrics.txt`) into the repository root.

Run the classifier (Python 3.8+, standard library only):

```
python classify.py data/transcripts.jsonl > predictions.csv
python classify.py data/transcripts.jsonl --out predictions.csv
```
