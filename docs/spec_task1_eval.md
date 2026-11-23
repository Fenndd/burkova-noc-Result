# Specification: Task 1 — "Eval: čo sa v každom hovore naozaj stalo"

Source of requirements: `README.md` (section "Úlohy → 1"), rules in `AGENTS.md`, reference — `data/labeled_sample.jsonl`.
Open questions and contested cases are moved to [contested_cases.md](contested_cases.md); once they are agreed, this specification is updated.

## 1. Goal

For every call in `transcripts.jsonl`, determine **exactly one** label — **with what outcome the caller left**.
Intermediate failures that the bot later fixed do not determine the label.

The classifier is needed for two things:
1. `predictions_night1.csv` (graded against the full labelling of night 1).
2. A live run on **another night's data** at the workshop (same format, but "something may change") → leaderboard.

## 2. Run contract

```
python classify.py <transcripts.jsonl> [--out predictions.csv]
```

- Without `--out` — CSV to stdout (README example: `> predictions.csv`); `sys.stdout.reconfigure(encoding="utf-8", newline="")`.
- Header `call_id,label`; **exactly one row per input line**, in input order.
- Python standard library only (3.8+ compatible, no tricks from newer f-string versions).
- A line parse error / unexpected structure → the row is still output with a fallback label, the reason is written to stderr. Empty lines are skipped.
- A summary of the label distribution → stderr (does not interfere with stdout redirection).
- Files are opened with `encoding="utf-8"`; the output file with `newline=""`.

## 3. Labels

| Label | When (README) | Structural sign in the events |
|---|---|---|
| `TRANSFERRED` | The bot transferred to dispatch, the dispatcher picked up | the last `transfer` has `status == "connected"` |
| `TRANSFER_FAILED` | The transfer attempt failed | the last `transfer` has any other status (`queue_full`, `timeout`, unknown) |
| `OUT_OF_SCOPE` | The caller wanted something else, the bot directed them elsewhere | there is a `route` (any `target`) |
| `TICKET_CREATED` | The outage is unknown, the bot created a ticket | `create_ticket` → `ok` |
| `KNOWN_OUTAGE_INFORMED` | Address found, outage known, the bot reported the status/ETA | `get_outage` → `ok` with a non-empty `outage_id` **and** after the result, before `hangup`, there is a `bot` utterance |
| `API_ERROR` | The bot could not help because of a `get_outage` / `create_ticket` failure | a failure (non-ok or no result) of `get_outage`/`create_ticket` after which no help was given |
| `ADDRESS_NOT_UNDERSTOOD` | The bot could not determine the address | there was a `resolve_address`, but no confirmed address (repeated `no_match`/`ambiguous`, or the address was rejected by the caller) and `get_outage` did not follow |
| `ENDED_EARLY` | The call ended early, without a tool/transfer failure | everything else: hung up at the greeting, did not give an address, left before the result was announced despite an ok response |

## 4. Algorithm (priority — "the outcome for the caller")

**§4 is the normative section.** If the table in §3 disagrees with §4, §4 applies.

We work from **structural events** (`tool_call`, `tool_result`, `transfer`, `route`, `hangup`), not from the bot's text.
The `bot` text is used only as the fact "the bot said something after the result"; wording is not compared.

**Known scenario (B14).** The label is determined only by the events of the known scenario: `resolve_address`, `get_outage`, `create_ticket`, `transfer`, `route`, `hangup`, `bot`/`caller` utterances. New/unknown tools and event types are **ignored completely**: neither their success nor their failure affects the label (for example, a failed `send_sms` after the status message → `KNOWN_OUTAGE_INFORMED`).

### 4.0. Preprocessing (recovery of broken data — §5.2)
- `t` is converted to a number (`float()`); an event without `t` gets the `t` of the previous event. If the events are already ordered by `t`, the file order is unchanged. If not — sort by (`t`, rank): `tool_call` = 0, `tool_result`/`transfer` = 1, everything else = 2 (on night 1 the result and the bot's utterance always have the same `t`, and without the rank a shuffled input breaks "the bot spoke right after the result").
- **End of call = the first `hangup`** (R2: the caller cannot return to the same call; on night 1 there is exactly one `hangup` per call). Subsequent `hangup`s are a log artefact and are ignored. No `hangup` → end = the last event.
- Events after the end of the call ("late" ones) were not heard by the caller. Only late `tool_result`s (A1, B3, B4) and a late `create_ticket` call with a successful result (round 6: the ticket was created after the caller left → it exists in the system) are taken into account. A late `transfer` and other late calls do not change the label (R7).
- **The bot is sequential** (R3: it always waits for the tool's response, on night 1 — 0 calls before the response to the previous one). The result of a call = the next `tool_result` with the same `name`.
- Statuses are compared after `strip().lower()`: `ok`, `connected`.
- "**The bot spoke right after the result**" = the first event of the known scenario after the `tool_result` (caller utterances and unknown events are skipped) is a `bot` utterance, and it is before the end of the call.
- Success/failure of a tool result is determined per §5.1.
- **Uncorrected failure** — a failure after which the same stage never succeeded: the address was not established (no `get_outage` followed), `get_outage` did not get a successful response on the last call, `create_ticket` did not get a successful response.

### 4.1. Step 1 — transfer to dispatch (B16, B17, S04)
There was at least one `transfer` **before the end of the call** → the **last** `transfer` decides:
- `connected` → `TRANSFERRED`;
- any other status, including unknown (B9) → `TRANSFER_FAILED`.

This holds regardless of what happened before or after the transfer: a ticket, a reported status, a `route`. A transfer attempt is a sign of a dangerous situation (1,026/1,026 on night 1, with no false positives and no misses). If a dangerous call did not get a dispatcher, it is `TRANSFER_FAILED` (B17, S04). A transfer with any `target` counts as a transfer: if the label were tied to the name of the target, renaming the target on night 2 would break all transfers.

### 4.2. Step 2 — other outcome episodes (B16)

| Outcome | Sign | Label |
|---|---|---|
| ticket created | a successful `create_ticket` (the result may also arrive after the end of the call — B3; the call itself may also be after the end of the call — round 6), **only if the outage was not known**: earlier in the call there is no successful `get_outage` with a non-empty `outage_id` (README: "porucha nebola známa a bot založil hlásenie"). A ticket must not be created when the outage is known; if there is one anyway, it does not count as an episode, and the reported status decides | `TICKET_CREATED` |
| known outage reported | a successful `get_outage` with a non-empty `outage_id` before the end of the call, and **the bot spoke right after the result**; ETA is not required (B11) | `KNOWN_OUTAGE_INFORMED` |
| directed elsewhere | a `route` with any `target` (B10), **if there was no uncorrected failure before it** (R6). Otherwise the `route` is a fallback after a failure, and step 3 decides | `OUT_OF_SCOPE` |

If there is at least one episode → label = **the last episode before the end of the call**. Tool failures before it were corrected and are not taken into account.

### 4.3. Step 3 — no episode: the last uncorrected failure decides
The flow is sequential, so the last failure is also "the furthest stage".

| Failure | Label |
|---|---|
| `create_ticket` failed or there is no result (B4) | `API_ERROR` |
| the last `get_outage` failed or there is no result — before or after the end of the call (A1) | `API_ERROR` |
| `get_outage` succeeded with an `outage_id`, the result is before the end of the call, but the bot did not speak — regardless of who hung up (B12) | `API_ERROR` |
| the outage is unknown, there is no ticket and no transfer, the bot ended the call: `hangup.by ∈ {bot, system}` (B13) | `API_ERROR` |
| the address was not established: there was a `resolve_address`, `get_outage` was not called, and in addition (there was a failed attempt, **or** attempts ≥ 2, **or** `hangup.by ∈ {bot, system}`). The number of attempts is not hard-coded (A2, B1, B8, R5). A `resolve_address` without a result is also a failed attempt | `ADDRESS_NOT_UNDERSTOOD` |

### 4.4. Step 4 — otherwise → `ENDED_EARLY`
This includes:
- hung up at the greeting / no address given (A5);
- the `get_outage` ok arrived **after** the end of the call (A1);
- the outage is unknown, but the caller left before `create_ticket` (B2);
- the address was found on the first attempt, but the caller left without confirming it;
- the caller hung up without waiting to be connected to the dispatcher, and no `transfer` is recorded before the end of the call (R7). If a ticket had been created before that — `TICKET_CREATED` per step 2.

## 5. Robustness for "night 2"

- Open sets: event types, tool names, statuses, `transfer.status`, `route.target`, `hangup.by`, `ended_by`, `flow_version`. An unknown value does not break the run.
- Repeats (`get_outage` after a timeout, several `transfer`s) — the **last** attempt decides (B5, B6).
- `calls.csv` is not used (on night 2 it may differ/be absent) — only the transcripts.
- We do not rely on specific bot wording or on the number of address attempts.
- Renaming of response fields (for example, `outage_id`) is not supported (R4, principle B14).

### 5.1. Tool success/failure — by signs, not by status (B7, B8)
We do not classify the status string. The only known success is `ok` (for a transfer — only `connected`). `result` is not a dictionary → no payload.
For any other status it is a **success** only if **all** conditions for its tool hold:

| Tool | Payload | The flow continued as after a success |
|---|---|---|
| `resolve_address` | non-empty `address_id` | the next call is `get_outage` (not a repeated `resolve_address`) |
| `get_outage`, outage known | non-empty `outage_id` | the bot spoke right after the result, `get_outage` was not called again |
| `get_outage`, outage unknown | the key `outage_id` is present and equals `null` | `create_ticket` or `transfer` followed, i.e. the bot took the "no outage" branch |
| `create_ticket` | non-empty `ticket_id` | the bot spoke right after the result, `create_ticket` was not called again |

Otherwise — a **failure**, interpreted by the role of the tool:
- a `resolve_address` failure is always the address branch, never `API_ERROR`;
- a `get_outage` / `create_ticket` failure without an outcome → `API_ERROR`.

An empty payload (`candidates: []`, `outage_id: null` without a continuation of the flow) is not a sign of success.
New tools are not considered (B14).

### 5.2. Invalid data (B15)
First we try to recover the outcome, the fallback is only if that failed:
1. The line does not parse → `call_id` by regex; events one at a time via `json.JSONDecoder.raw_decode`: after a successful parse we continue from the end of the object, after a failed one — from the next `{`. The file is opened with `encoding="utf-8-sig"` (in case of a BOM).
2. No `type` on an event → the type by fields: `args` → `tool_call`; `name`+`status` → `tool_result`; `by` → `hangup`; `asr_conf` → `caller`; `target`+`status` → `transfer`; only `target` → `route`; only `text` (without `asr_conf`) → `bot`.
3. Unstable order → stable sort by `t` (an event without `t` gets the `t` of the previous one — §4.0).
4. No `hangup` → end of call = the last event.
5. Duplicate `call_id`s → a row for every input line.
6. Recovery failed (no events / `events` is not a list, etc.) → **fallback `KNOWN_OUTAGE_INFORMED`** (the most frequent label — only for the sake of scoring at the workshop; see the caveat in contested_cases B15). If there is not even a `call_id` — `call_id` = `line-<line number>`.
7. Every recovery/fallback is written to stderr (`call_id`, what was fixed). A separate diagnostics file (`--diagnostics`) is a P2 task for task 2 and is **not implemented** in the classifier; `predictions.csv` always contains one of the 8 labels.

## 6. Verification (definition of done)

1. `labeled_sample.jsonl`: 60/60 matches, with the confusion matrix printed (script `scripts/eval_labeled.py` or the `--eval` flag).
2. The number of rows in `predictions_night1.csv` = 11,400 + header; all `call_id`s are unique and match the input.
3. The label distribution on night 1 is checked against the structural patterns from `scripts/profile_night.py` (each of the 37 patterns falls into one expected label).
4. Stress test on synthetically "corrupted" data: unknown status/event type/tool, a broken JSON line, missing `hangup`, missing `result`, `events` not a list → no crashes, as many rows as on the input.
4a. Synthetic calls for each case B1–B17, R1–R7, S04 from [contested_cases.md](contested_cases.md) and the review scenarios S01–S25 → the expected label from §4.
4b. Regression: the night 1 distribution matches §8 **exactly**.
4c. A run without `--out` (stdout) is checked byte by byte: UTF-8, header `call_id,label`, no `

`. A run via `python -I` also works.
4d. stderr has a summary of values that were not present on night 1: statuses, tools, event types, `hangup.by`, `transfer.status`, `route.target`, `flow_version`. At the workshop it immediately shows what changed in the data.
5. Re-check the sample after every classifier change.

## 7. What we deliberately do not do

- No LLM / NLP on the caller's text: structural events fully determine the label on all 60 labelled calls and on all 37 patterns of night 1; a model would add a dependency, non-determinism and risk on an unfamiliar machine.
- No analysis of `asr_conf` in the classifier (it is a cause of failures for task 2, not a label criterion).
- No external dependencies (pandas etc.).

## 8. Expected result on night 1 (by structural patterns, before implementation)

| Label | Count |
|---|---:|
| KNOWN_OUTAGE_INFORMED | 5,928 |
| TICKET_CREATED | 2,052 |
| ENDED_EARLY | 912 |
| TRANSFERRED | 798 |
| API_ERROR | 684 |
| ADDRESS_NOT_UNDERSTOOD | 456 |
| OUT_OF_SCOPE | 342 |
| TRANSFER_FAILED | 228 |
| **Total** | **11,400** |

These numbers are for cross-checking; the final ones will come from `classify.py`.

## 9. Change log

**Ed. 2 (23. 11. 2026), after round 2 of the review of [contested_cases.md](contested_cases.md):**
- §4: the fixed rule order (transfer → route → ticket → …) was replaced by "a successful outcome beats a failure; among successful ones — the last; without a success — the last uncorrected failure" (B16). On night 1 the result is the same (the 11,400 labels do not change).
- §4: added B12 (the bot stayed silent after ok → `API_ERROR`), B13 (outage unknown, the bot ended without a ticket → `API_ERROR`), B14 (failure of a new tool before the outcome → `API_ERROR`, awaiting confirmation), B2/B3/B4, clarification of B1.
- §4: B17 (transfer failed → ticket created) under the current rule gives `TICKET_CREATED` — this is my recommendation, the decision has not been made yet.
- §5: the earlier "an unknown tool is ignored" was refined (B14): it does not change the label after the outcome, but its failure before the outcome is `API_ERROR`. The earlier "success = only `ok`" was replaced by signs (§5.1).
- §5.2: new section — recovery of broken data and the `KNOWN_OUTAGE_INFORMED` fallback (B15).

**Ed. 3 (23. 11. 2026), after round 3 of the review:**
- §4: rule B16 changed from "a successful outcome beats a failure" to "the last outcome episode before `hangup`". `TRANSFER_FAILED` moved from step 2 to step 1 as an outcome episode. Labels on night 1 do not change.
- §4: added an exception B17 for the pair "ticket + failed transfer", variants (a)/(b) await a decision.
- §4: B14 confirmed (a tool failure without an outcome → `API_ERROR`), the ❓ sign removed.
- §5.2: diagnostics of broken logs are not implemented in the classifier (P2, only for task 2).

**Ed. 4 (23. 11. 2026), after round 4 of the review:**
- §4: B17 resolved — "ticket + failed transfer" → `TRANSFER_FAILED` (the sign of danger = a transfer attempt, verified on night 1 with no errors in either direction).
- §4, §5.1: B14 — new tools are ignored completely. The Ed. 3 line "failure of a new tool without an outcome → `API_ERROR`" was removed; the label is determined only by the known scenario.

**Ed. 5 (23. 11. 2026), after the independent review and round 5 ([contested_cases.md](contested_cases.md)):**
- §4 was rewritten as normative and split into steps 4.0–4.4.
  - 4.0: end of call — the **first** `hangup` (R2); the bot is sequential (R3); statuses are case-insensitive; the exact definition of "the bot spoke right after the result"; the definition of "uncorrected failure"; an event without `t` and equal `t`s.
  - 4.1: the transfer is decided by the **last** `transfer` before the end of the call, regardless of the ticket, the status and the `route`. Closes R1, B17 and S04; fixes an error of Ed. 4 where "the pair in any order" also fired on a repeated `connected`.
  - 4.2: `route` → `OUT_OF_SCOPE` only if there was no uncorrected failure before it (R6).
  - 4.3: ADDRESS and B13 use `hangup.by ∈ {bot, system}` (R5).
  - 4.4: the caller did not wait to be connected to the dispatcher → `ENDED_EARLY`, a late `transfer` is not taken into account (R7).
- §5: renaming of response fields is not supported (R4).
- §5.1: the conditions are spelled out per tool via "and". A non-ok status + `outage_id: null` = "no outage" only if the flow took that branch.
- §5.2: `raw_decode` continues from the end of the object; `utf-8-sig`.
- §6: added the review synthetics, the exact regression to §8, a byte-level stdout check, `python -I`, a summary of new values in stderr.

**Ed. 6 (23. 11. 2026), after the code review and round 6 ([contested_cases.md](contested_cases.md)):**
- §4.2: a ticket is an outcome `TICKET_CREATED` only if the outage was not known (a ticket must not be created when the outage is known, README).
- §4.0, §4.2: a `create_ticket` call after the caller left with a successful result → `TICKET_CREATED`.
- §4.0: sorting with the event rank — only for unordered input.
- §5.2: an event without `type` with only `text` → `bot`.
- Implementation fixes without a change of rules: R6 checks the furthest stage first (`create_ticket` before `get_outage`); the input is opened before `--out` is written; a lone `` inside a line does not split it; `call_id` from a broken line is decoded; `false` is not treated as a non-empty identifier.
- Night 2 risks from the code review (synonyms of success, a time shift by milliseconds, renamings) are deliberately not taken into account.
