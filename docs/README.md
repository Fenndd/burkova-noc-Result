# docs/ — guide

These are the working documents behind the short answers in [`TASKS_02-04.md`](../TASKS_02-04.md) and [`NOTES.md`](../NOTES.md). They are more detailed than the deliverables and are meant for a reviewer who wants to check a number or a decision.

- **Times** are local (Europe/Bratislava, UTC+1) unless marked `Z`.
- **Numbers.** Every number comes from a script in [`scripts/`](../scripts/README.md). The command is at the top of each document.
- **Data.** Running anything needs the assignment's `data/` folder in the repository root (see the root [`README.md`](../README.md)).
- **"The README" or "the brief".** Where a document says `README.md` (Slovak), the brief or "the assignment", it means the original assignment text. That text is not in this repository.

## Suggested reading order

1. [`task2_38_percent.md`](task2_38_percent.md): what the client's "38 %" is.
2. [`task2_failures_by_cause.md`](task2_failures_by_cause.md): the real failures by cause.
3. [`fix_backlog.md`](fix_backlog.md): who fixes what, the priorities and the order.
4. [`task4_switch_off.md`](task4_switch_off.md): whether to switch the bot off.
5. [`spec_task1_eval.md`](spec_task1_eval.md): how the classifier decides.

## Documents

| Document | What it is | Numbers from |
|---|---|---|
| [`spec_task1_eval.md`](spec_task1_eval.md) | **Task 1 specification**, the normative source for `classify.py`. Covers the run contract, the labels, the labelling algorithm (outcome for the caller), robustness for night 2, the definition of done, what we deliberately do not do, and the change log. | `scripts/profile_night.py`, `scripts/eval_labeled.py` |
| [`contested_cases.md`](contested_cases.md) | **Decision log** (temporary working file, kept for transparency). It holds the contested boundaries (A), combinations possible on night 2 (B) and observations for tasks 2–4 (C), plus six review rounds with my decisions. Rounds are only appended, never edited. Its results now live in the spec, `fix_backlog.md` and `TASKS_02-04.md`. | `scripts/profile_night.py` |
| [`task2_38_percent.md`](task2_38_percent.md) | **Task 2, item 1.** What the dashboard's "38 %" measures (`ended_by=bot`), what is inside it, the hour-by-hour picture, and examples to check by hand. | `scripts/task2_38_percent.py` |
| [`task2_failures_by_cause.md`](task2_failures_by_cause.md) | **Task 2, item 2.** Real failures by cause (`API_ERROR`, `ADDRESS_NOT_UNDERSTOOD`, `TRANSFER_FAILED`), the borderline `ENDED_EARLY` group, quality problems inside successful calls (stale ETA, ticket descriptions), and calls vs. people. | `scripts/task2_failures.py` |
| [`fix_backlog.md`](fix_backlog.md) | **Task 2, item 3 and task 4.** Full detail behind `TASKS_02-04.md`: owner of each fix (account team / product team / Voltika) with P0–P2 priorities, the order of work, the SMS phases, and the switch-off summary. | the task documents it links to |
| [`task4_switch_off.md`](task4_switch_off.md) | **Task 4, item 3.** Operator capacity against demand per hour, three scenarios, the OMS degradation window, and what would change the verdict. | `scripts/task4_capacity.py` |
| [`outage_consistency_evidence.md`](outage_consistency_evidence.md) | **Evidence for a human check.** `get_outage` gives contradictory answers for the same address. The document tests and rejects the legitimate explanations, then compares the answers with a random baseline. Its conclusion: the inconsistency is real in the data but may be an artefact of the fictional dataset. | `scripts/check_outage_consistency.py` |
| [`night2_network_drop.md`](night2_network_drop.md) | **Night 2 (in Russian).** The 75 calls cut by the network right after the first failed address attempt: the scenario, why they are `ADDRESS_NOT_UNDERSTOOD` today (spec 4.3, B1), why `ENDED_EARLY` fits better, and the decision N1 (applied in spec ed. 7). | `scripts/night2_network_drops.py` |

## Not committed: transcript dumps

Three readable dumps of full call transcripts were used during the review. They contain the assignment's call data, so they are git-ignored. Some documents above still link to them. To regenerate them locally:

```
python scripts/render_labeled.py
python scripts/render_calls.py data/transcripts.jsonl --filter address_rejected --out docs/calls_address_rejected.md
python scripts/night2_network_drops.py noc2/data/transcripts.jsonl noc2/data/calls.csv --out docs/calls_network_drop_night2.md
```

- `labeled_sample.md`: the 60 hand-labelled calls, grouped by label, with the colleague's notes.
- `calls_address_rejected.md`: the 60 "A2" calls, where the resolver found an address and the caller rejected it.
- `calls_network_drop_night2.md`: the 150 night-2 calls cut by the network (75 after a failed first address attempt, 75 after a found address).
