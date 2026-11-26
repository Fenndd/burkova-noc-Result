# scripts/ — guide

All scripts use only the standard library and are deterministic: two runs give identical output. Run them from the repository root, with the assignment's `data/` folder placed there. Output goes to stdout.

## Reproduce the deliverables (also on `master`)

| Script | Prints the numbers for |
|---|---|
| `task2_38_percent.py` | `TASKS_02-04.md` §2 "38 %", [`docs/task2_38_percent.md`](../docs/task2_38_percent.md) |
| `task2_failures.py [data_dir]` | `TASKS_02-04.md` §2 failures by cause, [`docs/task2_failures_by_cause.md`](../docs/task2_failures_by_cause.md) |
| `task4_capacity.py` | `TASKS_02-04.md` §4 switch-off, [`docs/task4_switch_off.md`](../docs/task4_switch_off.md) |

These scripts read `predictions_night1.csv`, the output of `classify.py`, and cross-check it against the classifier.

## Helpers (`full` only)

| Script | What it does |
|---|---|
| `eval_labeled.py` | Runs the classifier on `data/labeled_sample.jsonl`. Prints accuracy (60/60), the confusion matrix and any mismatches. Run it after every classifier change. |
| `profile_night.py [transcripts.jsonl] [calls.csv]` | Data profile of one night: structural call patterns and the checks behind [`docs/contested_cases.md`](../docs/contested_cases.md). It is also the first thing to run on a new night. |
| `check_outage_consistency.py [data_dir]` | Every number and case in [`docs/outage_consistency_evidence.md`](../docs/outage_consistency_evidence.md). The random baseline uses a fixed seed. |
| `verify_bot_ended.py` | Independent check that `calls.csv` `ended_by == bot` matches the transcripts (the basis of "38 % = who ended the call"). |
| `render_labeled.py [input] [--out]` | Writes the readable `docs/labeled_sample.md` (git-ignored). |
| `render_calls.py <transcripts> --filter address_rejected --out <md>` | Writes a readable subset of calls, e.g. `docs/calls_address_rejected.md` (git-ignored). |
| `night2_network_drops.py [transcripts] [calls.csv] [--out]` | Night 2: every number in [`docs/night2_network_drop.md`](../docs/night2_network_drop.md) (calls cut by `hangup.by = network`, decision N1) and the readable dump `docs/calls_network_drop_night2.md` (git-ignored). |

## Tests

```
python -m unittest discover -s tests
```

`tests/test_classify.py` has 91 cases. The synthetic calls are named after the decision ids in `docs/contested_cases.md` (A1, B14, …). The spec they test is [`docs/spec_task1_eval.md`](../docs/spec_task1_eval.md).
