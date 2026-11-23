# Agent instructions

`CLAUDE.md` imports this file; keep this file as the single source of truth for agent rules.

## What this is

A take-home assignment ("Búrková noc", Born Digital @ Night of Chances 2026). `README.md` (in Slovak) is the full brief — read it first; it wins over this file if they disagree. We play a forward deployed engineer on the **Voltika** account (electricity distributor) after a storm night (Sun 15. 11. 2026, 11 400 calls vs. ~300/day normally). The client claims the AI voicebot "hung up on 38 % of calls" and will decide by Wednesday whether to switch it off.

Time box is 2–3 hours; judgment ("what I deliberately did not do and why") is graded alongside accuracy. Prefer simple, explainable solutions over elaborate ones.

## Deliverables (repo must contain)

1. **Classifier** — one command, e.g. `python classify.py data/transcripts.jsonl --out predictions_night1.csv`. Also keep writing to stdout when `--out` is omitted (the README example uses `> predictions.csv`, and the graders may run it that way on their machine). Output CSV header `call_id,label`, exactly one row per input call.
2. `predictions_night1.csv` — committed output for night 1 (11 400 rows plus header).
3. One markdown with tasks 2–4: numbers (≤ ½ page: what "38 %" means, real failures by cause, who owns each fix — us on the account / our product team / Voltika), the client email (≤ 200 words, ready to send, honest, no promises we can't keep), next steps (3–5 bullets incl. the SMS request and whether to turn the bot off — compare against 3 night operators × 60/4 min ≈ 45 calls/h vs. a ~2 600/h peak).
4. `NOTES.md` — assumptions, what I'd do with more time, how AI tools were used (what was delegated, what was verified by hand, one place the agent was wrong).

Written deliverables for the client are in Slovak. Every number in the deliverables must be reproducible from the data by a script in the repo; derive conclusions from the data during the task rather than from this file.

## Data (`data/`)

- `transcripts.jsonl` — one JSON per line: `{"call_id", "events": [...]}`, events time-ordered, `t` = seconds from call start. Event types: `bot`, `caller` (`text`, `asr_conf`), `tool_call` (`name`, `args`), `tool_result` (`name`, `status`, `latency_ms`, `result`), `transfer` (`target`, `status`), `route` (`target`), `hangup` (`by`). Failed `tool_result`s may have no `result` field.
- `labeled_sample.jsonl` — 60 hand-labeled calls (`call_id`, `label`, optional `note`, `events`). This is the ground-truth reference for edge cases; always check accuracy against it after changing the classifier.
- `calls.csv` — per-call metadata the client's dashboard is built from (`started_at` in **UTC**; Voltika is Europe/Bratislava, UTC+1). The README's "19:00–01:00" is local time, i.e. 18:00–00:00 UTC.
- `oms_api_metrics.txt` — Voltika's `get_outage` API metrics in 5-min UTC buckets. Night 1 has a degradation window from the 20:40Z bucket through the 21:25Z bucket (p95 at the 8 s cap, ~26–36 % errors), with a partial tail in the 21:30Z bucket (p95 ~7 s, ~4 % errors) — i.e. about 21:40–22:35 local time. Use local time when talking to the client.

Observed values on night 1 (useful, but **not exhaustive**):
- tool statuses: `resolve_address` ok/`no_match`/`ambiguous`; `get_outage` ok/`timeout`; `create_ticket` ok/`timeout`
- `get_outage` ok result: a non-null `outage_id` = known outage (on night 1 it always came with an `eta`, but `eta` is not required for `KNOWN_OUTAGE_INFORMED` — the README says "status or ETA"); `outage_id: null` = unknown → should lead to `create_ticket`
- transfer: `dispatch` with `connected` / `queue_full` / `timeout`; route: `customer_line`; hangup by: `caller`/`bot`/`system`; `flow_version`: only `v14`
- up to 3 `resolve_address` calls per call on night 1 (the retry limit is a flow detail and may change)
- some `tool_call`s have no matching `tool_result` (caller hung up while waiting)

## Classification rules (task 1)

Exactly one of: `KNOWN_OUTAGE_INFORMED`, `TICKET_CREATED`, `TRANSFERRED`, `TRANSFER_FAILED`, `API_ERROR`, `ADDRESS_NOT_UNDERSTOOD`, `OUT_OF_SCOPE`, `ENDED_EARLY`. **The outcome for the caller decides**, not intermediate failures that were later recovered. Precedents from the labeled notes:

- Address found only on a later retry, then outage reported → `KNOWN_OUTAGE_INFORMED`.
- The bot never established the caller's address and gave up (repeated `no_match`/`ambiguous`, or the resolver returned an address the caller rejected) → `ADDRESS_NOT_UNDERSTOOD`. Do not hard-code the number of attempts.
- `get_outage` timeout and bot apologised/hung up → `API_ERROR`; also when the caller hung up while waiting on `get_outage` (result never came, or it later timed out).
- Outage unknown but `create_ticket` timed out → `API_ERROR`.
- Caller hung up before the bot spoke the status even though the tool returned ok → `ENDED_EARLY`; also hung up at the greeting, or never gave an address.
- Transfer `queue_full` or `timeout` → `TRANSFER_FAILED`.

## Robustness for night 2 (important)

At the workshop the classifier is re-run live on **another night's data** in the same format, but "something may change". Design for it:
- Treat status lists, `ended_by`/`hangup.by` values, transfer statuses, route targets, event types, tool names and `flow_version` as **open sets**; unknown values must not crash the run.
- Interpret a tool failure by the tool, not by the status string: a failed `resolve_address` is an address problem (retry or `ADDRESS_NOT_UNDERSTOOD`), never `API_ERROR`; a failed `get_outage`/`create_ticket` that leaves the caller without help is `API_ERROR` (per README). For an unknown status, look at what happened next (did the bot still announce the status, create a ticket, retry?) rather than assuming success or failure. Only `connected` counts as a successful transfer.
- Never drop a call: catch per-line errors and still emit a fallback label so the row count matches the input.
- Don't key logic on exact bot phrasing if a structured event carries the same information; if bot text is needed, match loosely.
- Prefer the Python standard library only (unknown environment at the workshop).

## Windows gotchas (this machine)

- Console is cp1252: printing Slovak text crashes Python with `UnicodeEncodeError`. In scripts call `sys.stdout.reconfigure(encoding="utf-8", newline="")`; `PYTHONIOENCODING=utf-8` also works but is ignored under `python -I`/`-E`. Always open files with `encoding="utf-8"`.
- Windows PowerShell 5.1 `>` writes UTF-16. For local runs use the classifier's `--out` option (or run the redirect from the Bash tool).
- `csv.writer` on Windows stdout produces `\r\r\n` unless `newline=""` is set (open output files with `newline=""` too).

## Git and submission

- Git repo on branch `master`; the submission is a link to this repo (or a zip). Deadline: Mon 23. 11. 2026, 23:59.
- Do not commit or push unless the user asks.
