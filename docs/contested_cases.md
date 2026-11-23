# Contested points in the night 1 data — for review

> **Note on this file.** `contested_cases.md` is a temporary working file, kept here for transparency. I use this kind of file in development during planning and decision-making sessions. Once every detail has been discussed, the useful information is moved to its proper place in the documentation, tasks are created, and the file is deleted.

All numbers are reproducible: `python scripts/profile_night.py` (night 1, 11,400 calls).
Readable sample: [labeled_sample.md](labeled_sample.md). Specification: [spec_task1_eval.md](spec_task1_eval.md).

**Main conclusion.** Night 1 has only 37 structural event patterns, and in the 60 labeled calls the label is **unambiguously** determined by structure (no pattern received two different labels). So the contention is not about "guessing" but about a few **boundary decisions** (A) and **combinations that do not occur on night 1 but may appear on night 2** (B). Separately, there are observations that do not affect the label but matter for tasks 2–4 (C).

Format: ✅ = settled by a precedent from the labeled sample, ❓ = needs your decision (my recommendation is given).

---

## A. Contested boundaries that occur on night 1

### A1. The caller hung up while waiting for `get_outage` — 337 calls ✅
| What happened next | Calls | Wait until hangup (min/median/max) | Label per labeled sample |
|---|---:|---|---|
| result arrived later, `ok` | 273 | 0.9 / 2.3 / 6.9 c | `ENDED_EARLY` (c-n1-002134, 005010, 006726) |
| result arrived later, `timeout` | 32 | 4.6 / 5.7 / 7.5 c | `API_ERROR` (c-n1-005305, 006802) |
| no result at all | 32 | 4.6 / 6.2 / 7.4 c | `API_ERROR` (c-n1-005115, 009965) |

The contention: in all three cases the caller left without hearing anything; the label is determined by **what the caller did not see** (the API outcome). The waiting times overlap (4.6–7 s also occurs with `ok`). I follow the labeled sample — the "API outcome decides" rule, without a time threshold.
Consequence for night 2: events **after** `hangup` must not be discarded; they are needed for the decision.

### A2. The address was found by the resolver, but the caller rejected it — 60 calls ✅
Pattern `resolve ok → "nie…" → resolve ok → "nie…" → hangup:bot`, without `get_outage`. Labeled sample: `ADDRESS_NOT_UNDERSTOOD` (c-n1-002946, 004109, 008650).
The contention: the tool returned `ok`, i.e. by statuses "everything is fine". I detect it structurally: "there was a `resolve_address`, but `get_outage` was never called", without parsing the word "nie".

### A3. Outage unknown → transfer to dispatch instead of a ticket — 514 calls ✅
`get_outage ok (outage_id=null)` → bot "Opíšte, čo sa stalo" → the caller described a hazard → `transfer` (400 `connected`, 80 `queue_full`, 34 `timeout`). **No ticket is created** in this case.
Labeled sample: `TRANSFERRED` / `TRANSFER_FAILED` (c-n1-003792, 010326). Transfer takes precedence over a ticket.
The contention for task 2: in the 114 calls with a failed transfer, a person with a hazardous situation left with **nothing** — neither a dispatcher nor a ticket.

### A4. Repeated failed address attempts, then success — 593 calls ✅
1–2 `no_match`/`ambiguous`, then `ok` and a reported status → `KNOWN_OUTAGE_INFORMED` (c-n1-001428, 003532, 006384, 008169).

### A5. Hung up at the greeting / did not give an address — 639 calls ✅ (but see C4)
365 — silence, 274 — a single utterance "haló", "počujete ma", "ehm", "no". The bot did **not answer** it, and the caller hung up after 3–5 s. Labeled sample: `ENDED_EARLY` (c-n1-005262, 005658, 007847, 011390).

### A6. Known outage and the caller hung up on their own — 2,900 calls ✅ (checked, not contested)
Concern: the person might have hung up before hearing the status. Check: between the bot's status utterance and the hangup there are at least 5.9 s (median 7.6 s) → the status was spoken. `KNOWN_OUTAGE_INFORMED`. Likewise for tickets (2,052, min. 6.5 s).

---

## B. Combinations that do not occur on night 1 but are possible on night 2 ❓

| # | Situation | My recommendation | Why |
|---|---|---|---|
| B1 | After `no_match`/`ambiguous` the **caller** hung up (the bot had not given up yet) | `ADDRESS_NOT_UNDERSTOOD` | There was an address resolution failure and the person left without help; README: ENDED_EARLY only when "there was no tool failure". |
| B2 | Outage unknown, the caller hung up before `create_ticket` | `ENDED_EARLY` | The tools worked fine, the caller just did not wait. |
| B3 | `create_ticket` → `ok`, but the result arrived **after** the hangup (number not spoken) | `TICKET_CREATED` | The ticket really exists — for the caller the outage is registered. The asymmetry with A1 is intentional: there the information was only "for the ears", here there is a real artifact. |
| B4 | `create_ticket` called, no result / timeout after the hangup | `API_ERROR` | Analogy with A1 (get_outage without a result). |
| B5 | `get_outage` timeout, the bot retried and got ok + reported it | `KNOWN_OUTAGE_INFORMED` / `TICKET_CREATED` | The outcome for the caller; the last attempt decides. |
| B6 | Several `transfer`s (e.g. `queue_full`, then `connected`) | By the **last** one | The outcome for the caller. |
| B7 | Unknown `get_outage`/`create_ticket` status (`error`, `rate_limited`, `503`…) | Look at what came next: a result was there + the bot reported it → success; otherwise `API_ERROR` | AGENTS.md: "by the tool and by what came next". |
| B8 | Unknown `resolve_address` status (`low_confidence`, `error`) | Address branch (retry / `ADDRESS_NOT_UNDERSTOOD`) — never `API_ERROR` | The resolver is our address tool; README lists only `get_outage`, `create_ticket` for API_ERROR. |
| B9 | New `transfer.status` (`busy`, `rejected`, `no_answer`) | `TRANSFER_FAILED` | Success is only `connected`. |
| B10 | New `route.target` (`web`, `sms`, `billing_line`) | `OUT_OF_SCOPE` | The meaning "sent somewhere else" does not depend on the target. |
| B11 | `get_outage ok` with `outage_id`, but **without `eta`** | `KNOWN_OUTAGE_INFORMED` | README: "stav alebo odhad". |
| B12 | `get_outage ok` with `outage_id`, the bot said nothing afterwards, hangup:bot | `API_ERROR`? / `ENDED_EARLY`? | ❓ No precedent. I recommend `ENDED_EARLY` for hangup:caller and `API_ERROR` for hangup:bot/system (the bot "broke" after ok) — **needs your decision**. |
| B13 | Outage unknown, the bot ended the call **itself** without a ticket and without a transfer (flow change) | `API_ERROR`? | ❓ No precedent. The person was left without help through no fault of their own; closest to "zlyhal nástroj". The alternative is `ENDED_EARLY`. |
| B14 | New tool (e.g. `send_sms`) | Ignore when choosing the label | Not part of the label definitions. |
| B15 | No `hangup`, a broken line, no `call_id` | Fallback, the row is still output | ❓ Which fallback: I recommend `ENDED_EARLY` (honestly "nothing happened"); by frequency `KNOWN_OUTAGE_INFORMED` (52 %) would be more accurate, but that is "guessing". |
| B16 | `transfer` and `route` in the same call | What came **last** before the hangup decides | The outcome for the caller. Currently in the specification transfer takes priority — I will fix it if you agree. |

---

## C. Observations that do not affect the label (for tasks 2–4)

**C1. What "38 %" means.** `ended_by=bot` = 4,332 of 11,400 (38.0 % — the client quotes the figure correctly). But of these, **3,028 (70 %) are a routine goodbye after the outage status was reported**. Real failures where the bot hung up: 620 `API_ERROR` + 456 `ADDRESS_NOT_UNDERSTOOD` + 228 `TRANSFER_FAILED` = 1,304 (11.4 % of all calls). Plus 64 `API_ERROR` where the caller hung up. The `ended_by` metric does not reflect the outcome.

**C2. Stale ETA — 377 of 5,928 reported outages.** The bot said "power will be back around 23:00" after 23:00 (279) and "around midnight" after midnight (98). The label stays `KNOWN_OUTAGE_INFORMED` (README: reported status/ETA), but it is a bad experience. The data belongs to Voltika (OMS), the voicing of a past time is our product. Important for the SMS request: an SMS with a stale ETA is worse than one without it.

**C3. A bug in tickets — 2,112 / 2,112 (100 %).** `create_ticket.args.description` receives the **bot's utterance** ("Na vašej adrese zatiaľ poruchu neevidujeme. Opíšte mi prosím…") instead of the caller's description. Not one ticket of the night contains a description of the problem. The owner is us (the flow on the account / product). It does not affect the label.

**C4. The bot is silent on "haló / počujete ma" — 274 calls.** A possible audio/latency problem or a missing reprompt. The label is `ENDED_EARLY` per the labeled sample, but for task 2 this is a candidate for "our fault", not "the caller changed their mind".

**C5. Address failures = speech recognition.** `asr_conf` of the utterance before `resolve_address`: with `ok` the mean is 0.90 and 0 % below 0.6; with `no_match` — 0.61 (49.5 % below 0.6); with `ambiguous` — 0.60 (55.6 %). The cause of `ADDRESS_NOT_UNDERSTOOD` is ASR/the resolver (our product), not Voltika's address registry (to be spot-checked).

**C6. `get_outage` failures:** 533 of 592 timeouts fall in 21:40–22:30 local time (by response time) — this matches the OMS degradation window in `oms_api_metrics.txt` (≈ 21:40–22:35 local); outside the window there are only background single digits. The owner is Voltika; our part is the lack of a fallback (e.g. create a ticket right away or offer a callback).

**C7. Repeat calls.** 10,300 unique numbers; 815 called more than once (1,915 calls, maximum 8 from one number). "Calls with a failure" ≠ "people left without help" — worth counting both for task 2.

**C8. Transfer.** 1,026 attempts, 228 failed (160 `queue_full`, 68 `timeout`). The Voltika queue is limited to 10 — Voltika is the owner; for us — a fallback on `queue_full` (a ticket with "hazard" priority).

---

## What we need from you

1. Confirm A1–A6 (I follow the labeled sample) — or object.
2. Decide **B12, B13, B15, B16**; for the other B items, confirm the recommendations.
3. Language of the specification/these notes: keep in Russian as working documents or translate into Slovak for the repository?


---
---

# Round 2 — answers to the review (23. 11. 2026)

The new numbers are reproducible with the same `python scripts/profile_night.py`, output section `ROUND 2`.
The A2 calls in readable form — [calls_address_rejected.md](calls_address_rejected.md) (`python scripts/render_calls.py data/transcripts.jsonl --filter address_rejected --out docs/calls_address_rejected.md`).
Tasks with priorities are moved to `TASKS_02-04.md`.

## Summary of decisions

| # | Decision | Task |
|---|---|---|
| A1 | ✅ Follow the labeled sample | our team (the account team) **P1**: the bot tells the caller it is checking, instead of staying silent |
| A2 | ✅ `ADDRESS_NOT_UNDERSTOOD`; calls exported | see C5 (resolver) |
| A3 | ✅ `TRANSFERRED`/`TRANSFER_FAILED` | our team (the account team) **P0** (= the fallback from C8) |
| A4, A6 | ✅ | — |
| A5 / C4 | ✅ `ENDED_EARLY` — answer below | proposal: our team (the account team), reprompt (priority is your decision) |
| B1, B3–B6, B9–B11 | ✅ Recommendations accepted (no objections) | — |
| B2 | ✅ `ENDED_EARLY` | our team (the account team) **P2**: `create_ticket` in this case too (needed for SMS) |
| B7, B8 | Answer below: we do not guess the status, we decide by features | — |
| B12 | ✅ `API_ERROR` regardless of who hung up | — |
| B13 | ✅ `API_ERROR` | — |
| B14 | Clarification below: the label is never ignored | — |
| B15 | ✅ We recover what we can; fallback `KNOWN_OUTAGE_INFORMED` | our team (the account team) **P2**: diagnostics of broken logs |
| B16 | Answer below + new question **B17** | — |
| C1 | ✅ Independently rechecked: **69.9 %** | — |
| C2 | ✅ | our team (the account team) **P1**: check for a stale ETA; Voltika: fix the ETA in the OMS |
| C3 | ✅ | our team (the account team) **P0**: the caller's description goes into the ticket; product team: validation in `create_ticket` |
| C5 | ⚠️ Objection: "almost all because of ASR" is not confirmed by the data | product team: ASR **and** resolver |
| C6 | ✅ | our team (the account team) **P0**: fallback on `get_outage` failure; mention in the email |
| C7 | ⚠️ Rule accepted, but with an amendment | our team (the account team) **P2**: dashboard |
| C8 | ✅ with clarifications | our team (the account team) **P0**: fallback on `queue_full`; discuss the "hazard" priority with Voltika |

## Answers to the questions

### A5 / C4. Did the bot speak the greeting?
**Yes, in all 639 calls** the first utterance is the bot's greeting at t = 0.0 s. After that there are two different cases:
- **365 calls — the caller was silent** and hung up at 1.5–5.0 s (median 3.4 s). Usually the caller starts speaking at 6.9–8.7 s, i.e. the greeting lasts ≈ 6–7 s. These people hung up **in the middle of the greeting**, before the question about the address. The logs show no fault of the bot (other than the greeting being long).
- **274 calls — the caller said something** ("haló", "počujete ma", "ehm", "no") at 6.9–8.7 s, **the bot answered nothing**, and after 1.1–4.8 s (median 2.9 s) the caller hung up. For comparison: normally the bot reacts to an utterance after 1.8 s (median), p95 — 3.6 s.
  - 31 callers hung up faster than the bot's usual reaction time — here the bot simply did not have time.
  - **68 waited longer than p95 (> 3.6 s)** — the bot clearly did not react. It looks like the bot has no branch for an utterance without an address (no reprompt like "Nepočula som vás, povedzte mi prosím adresu").
  - "počujete ma" (56) — the caller could not hear the bot. The logs cannot show whether this is the connection or the audio; audio logs are needed.
- The label per the labeled sample stays `ENDED_EARLY`. I propose a task for our team (the account team) — a reprompt on an utterance without an address. You decide the priority; I did not set it.

### B7, B8. How to distinguish unknown statuses?
We do not — and this is intentional. **We do not classify the status string at all**, except for one known success (`ok`, and `connected` for a transfer). For any other status the decision is made by **features in the events**, not by the status name:

| Feature | Success | Failure |
|---|---|---|
| Payload | `result` contains the expected key: `address_id` / key `outage_id` / `ticket_id` | there is no `result`, or it is empty (`candidates: []`) |
| The flow moved on | a next step with this result: `get_outage` with this `address_id`; the bot spoke right after the result; `create_ticket` after "outage unknown" | a retry of the same tool; the bot apologised and hung up; the next step did not happen |
| Call outcome | there is a successful outcome (status reported, ticket, transfer) | there is no outcome |

Then the failure is interpreted **by the tool's role**: a `resolve_address` failure is always the address branch (B8); a `get_outage`/`create_ticket` failure without an outcome is `API_ERROR` (B7).
Examples: `status: "degraded"`, `outage_id` present, the bot spoke immediately → counted as success → `KNOWN_OUTAGE_INFORMED`. `status: "rate_limited"`, no `result`, the bot apologised → `API_ERROR`. `status: "OK"`/`"success"` also pass as success by the features, without a synonym dictionary.
Limitation: if a new status means a "partial success" that the bot voiced incorrectly, the logs cannot distinguish it. I acknowledge this as a limitation and do not try to guess.

### B12. Accepted: `API_ERROR` regardless of who hung up
The data supports your logic: on night 1 the bot **always** speaks at the very moment the result arrives (gap 0.0 s in 22,868 of 22,868 cases). So "an ok result arrived before the hangup and the bot said nothing" is always a bot anomaly or a fake ok, not "the caller did not wait".
One boundary: if the result arrived **after** the hangup, A1 applies — `ENDED_EARLY` on ok. This does not contradict B12: there the bot did not have time, here the bot stayed silent.

### B14. Unknown tool — the label cannot be ignored
An inaccuracy in my wording: I meant "an unknown tool **does not change** the label", not "the label is ignored". By the task definition **each call gets exactly one of the 8 labels** — the label cannot be ignored, there can be no ninth label in the output.
The rule, clarified per your remark:
- `send_sms` (or any new tool) **after** the outcome (status reported / ticket created) → label by the outcome: `KNOWN_OUTAGE_INFORMED` / `TICKET_CREATED`, even if `send_sms` failed. The caller already received the outcome; an SMS failure is a metric of the SMS feature, not a label.
- A new tool **failed before the outcome**, and the caller left without help → `API_ERROR`. README lists `get_outage`, `create_ticket` in parentheses — I read this as examples, not a closed list. ❓ This is for your confirmation.
- A new tool with no influence on the flow (logging etc.) → not taken into account.

### B15. Accepted, with two caveats
What we recover from malformed data (into the specification):
1. The line does not parse as a whole → look for `call_id` with a regex; try to extract events one by one (`json.JSONDecoder.raw_decode` from each `{` inside `events`).
2. The event has no `type` → infer the type from the fields: `args` → `tool_call`; `name`+`status` → `tool_result`; `by` → `hangup`; `asr_conf` → `caller`; `target`+`status` → `transfer`; only `target` → `route`.
3. Events out of order → stable sort by `t` (without `t` — stays in place).
4. No `hangup` → the end of the call = the last event.
5. `events` is not a list / empty / no `call_id` → fallback.
6. Duplicate `call_id` → a row for each input line (the "one row per input" contract).

Caveats:
- **The `KNOWN_OUTAGE_INFORMED` fallback** maximizes expected accuracy only if the broken lines are random. If logs break precisely when the call fails (which is plausible), the fallback will be wrong more often than average. There is no better alternative without data — I accept your choice for the workshop.
- **Task P2 "label for broken data":** a ninth label cannot be written to `predictions.csv` — the leaderboard format has 8 labels. I propose a separate output (`--diagnostics diag.csv`: `call_id, issue, fallback_used`) and a separate row in the dashboard, while keeping one of the 8 in the CSV.

### B16. How `route` and `transfer` work, and how they can meet in one call
- **`route` is not a call transfer but a verbal redirection.** Before `route` the bot always (342/342) says: "S tým vám na poruchovej linke neviem pomôcť. Zavolajte prosím na zákaznícku linku 0800 123 456, platí cez pracovné dni." After `route`, in all 342 calls only the caller's `hangup` follows: they were dictated a number and hang up themselves. Incidentally: at night the bot sends people to a line that operates on **working days**.
- **`transfer` is a technical transfer into the Voltika queue.** The bot says "Prepájam vás na dispečing, nezatvárajte", then the caller waits 5.9–65.1 s (median 25 s) until the `transfer` event. During this time there is **not a single caller utterance** (0 of 1,026): the bot does not listen to the caller in the meantime (or does not log it). On `connected` the `system` hangs up — the bot leaves the call.
- **On night 1 they never occur together.** Theoretically it is possible:
  1. Two topics in one call: first a question about a bill (`route`), then "and also a pole is sparking" (`transfer`) — if the flow keeps listening after `route`.
  2. A new fallback after a failed transfer → redirection to another line (`route`).
  3. **Your own P0 fallback (C8): `transfer queue_full` → `create_ticket`.** The most likely candidate for night 2.
- The rule (clarification of B16): **the outcome before the hangup decides, with a successful outcome taking precedence over a failed one; among several successful ones — the last.** This generalizes the current order and gives the same 11,400 labels on night 1.

### New question B17 ❓ — the transfer failed, but a ticket was created (your fallback from C8)
`transfer queue_full` → `create_ticket ok` → the bot reports the ticket number. Options:
- `TICKET_CREATED` — README: "vyber ten, ktorý najlepšie popisuje, s čím volajúci odišiel", and the caller left with a ticket. **My recommendation.**
- `TRANSFER_FAILED` — the person with a hazardous situation never got a dispatcher.
The choice determines whether the dashboard sees the fallback as a fix. With `TICKET_CREATED`, the "transfer failed" metric is counted separately from events, not from labels.

## Recheck and clarifications to C1–C8

### C1. Independently rechecked — confirmed, with one amendment
A separate subagent wrote a check from scratch without seeing my scripts; the result matched. `ended_by=bot` 4,332 / 11,400 = 38.0 %, discrepancies `calls.csv` ↔ `hangup.by` — 0.

| What was in the calls where the bot hung up | Calls | Share |
|---|---:|---:|
| Reported a known outage → goodbye | 3,028 | **69.9 %** |
| `API_ERROR` (`get_outage` timeout 560, `create_ticket` 60) | 620 | 14.3 % |
| `ADDRESS_NOT_UNDERSTOOD` | 456 | 10.5 % |
| `TRANSFER_FAILED` | 228 | 5.3 % |

Evidence of "routine" for the 3,028 calls: the bot said the status in all of them; the caller's reply is only "dobre ďakujem" / "ďakujem" / "aha dobre" (not a single question the bot would have ignored); the bot's last utterance is "Ďakujem za zavolanie, dovidenia." / "Ďakujeme, dovidenia."; from the last event to the hangup 1.7–3.2 s.
**Amendment:** in 182 of these 3,028 calls the bot gave a **stale ETA** (C2) — the goodbye is routine, the information is wrong. The subagent did not notice this: it compared the ETA with the start of the night (18:00Z), not with the moment of the call. One of the places where the agent was wrong — useful for NOTES.md.

### C2. Agreed; clarification
I did not propose transferring to dispatch; I agree it is unnecessary load — dispatchers have the same OMS data.
Scale: the ETA was stale by 0–120 min (median 43 min); in 195 calls the caller ended the call, in 182 the bot. Instead of the past tense the bot can say: "poruchu evidujeme, technici na nej pracujú, aktuálny odhad obnovy zatiaľ nemáme". Then no past tense will go into the SMS either.

### C3. Agreed; proposal
The caller's description **is in the transcripts** — the utterance right after "Opíšte mi prosím, čo sa stalo" (5 typical ones: "nejde nám elektrina od večera", "vyhodilo ističe…" etc.). I propose a one-off task for our team (the account team) within P0: **backfill the description in the 2,052 tickets of night 1** from the transcripts and pass them to Voltika — technicians are currently going out to tickets without a description.
Also checked: all hazardous descriptions went to a transfer, all ordinary ones to a ticket; not a single hazardous situation was wrongly filed as an ordinary ticket.

### C5. ⚠️ Objection: ASR is the main cause, but not the only one
Your thesis: "almost all address failures are due to speech recognition → P0 of the product team". The data shows **two causes**:

| Group of `ADDRESS_NOT_UNDERSTOOD` (456) | Calls | Share | Probable cause |
|---|---:|---:|---|
| all attempts with `asr_conf` < 0.8 | 247 | 54 % | speech recognition |
| at least one attempt well recognized (≥ 0.8), but the resolver did not find it | 149 | 33 % | resolver/registry |
| the resolver found the **wrong** address (A2), `asr_conf` ≥ 0.7, mean 0.81 | 60 | 13 % | resolver/registry |

Evidence in favor of the resolver:
- Parts of settlements ("Grinava", "Cajla" — parts of Pezinok; "Kráľová", "Harmónia" — parts of Modra) show **50–57 % failed attempts** against a mean of 17.8 %. "Limbach" — a separate settlement — 10 %.
- Among well-recognized but failed attempts, 58.5 % (100/171) contain such a part of a town.
- In A2, in all 60 calls the resolver returned a street with the same name **in another town** and the same `address_id` on both attempts; the callers answered "nie nie ja som z inej obce". Example c-n1-000781: "vinohradnícka 19 pezinok cajla" → "Vinohradnícka 39, Ivanka pri Dunaji".
- Low `asr_conf` ≠ wrong text: the text of failed low-confidence attempts often looks correct ("bernolákovo ľudovíta štúra 18"). Possibly the problem is not an ASR error but that the resolver rejects uncertain input.

Proposal on owners (for your decision):
- **Product team, P0:** the resolver does not know parts of settlements and substitutes a same-named street in another town (`resolve_address` is, per README, "prevádzkujeme my"). Affects ≈ 209 calls (149 + 60) and part of the 247.
- **Product team, P1:** ASR / confidence threshold on noisy calls (≈ 247 calls). I agree that this is not exclusively our team (the account team).
- **Voltika — question:** whether parts of settlements exist in the address registry they supply to us. If not — that is their part.

### C6. Agreed
The OMS degradation window (≈ 21:40–22:35 local, 533 of 592 timeouts) goes into the email to the client. P0 — our fallback on `get_outage` failure.

### C7. ⚠️ I accept the "last call" rule, but it hides failures
Data on the 815 repeat callers (labels are structural, matching the labeled sample 60/60):
- **526** people got help only in the **last** call after a failed one. Under the "last call" rule their earlier **703 failed calls vanish** from the dashboard, although each is a bot failure and extra load on the line.
- **51** people got help **earlier**, and the last call was without help (often `ENDED_EARLY`: called back, listened and hung up). Under the rule they land in the dashboard as a failure, although they were helped.
- 69 people got no help in any call.

Proposal: in the "by people" dashboard take the person's **best outcome** (or the last meaningful one, excluding `ENDED_EARLY`), and keep a second metric next to it — "repeat calls caused by a failure". Otherwise the dashboard will overrate the bot (hiding 703 failures) and at the same time punish it for 51 repeat calls.

### C8. Agreed with the fallback; three clarifications
1. **Ordinary tickets do not go to dispatch at all.** All 1,026 transfers are hazardous situations ("spadnutý drôt", "iskrí to zo stĺpa", "horí rozvodná skriňa"…); an ordinary unknown outage always goes to a ticket without a transfer. There is no "ordinary ticket + queue full" branch in the flow. The "ordinary / hazard" split is needed in the **tickets** and in the Voltika queue, not in the transfer fallback.
2. **Offering a transfer again right after `queue_full` at the peak is pointless** — the queue is most likely still full. Currently the bot tells a person with a downed wire "Skúste prosím zavolať o chvíľu znova" — this is dangerous and generates repeat calls. I propose: a ticket with "hazard" priority → announce the number and that dispatch sees it with priority → **one** automatic retry of the transfer after N seconds if the queue has freed up → in case of danger to life/fire — advise calling 112. Agree this with Voltika: it is a safety issue, not just UX.
3. **In 114 of the 228 failed transfers there is no address** — a direct transfer right after the hazard description, without `resolve_address`. The "create a ticket" fallback must first ask for the address, otherwise a ticket cannot be created.

## What we need from you (round 2)
1. **B17** — the label for "transfer failed → ticket created".
2. **B14** — confirm: failure of a new tool before the outcome → `API_ERROR`.
3. **C5** — accept the split "resolver P0 / ASR P1" or keep ASR as P0.
4. **C7** — "best outcome per person" + a repeat-call metric, or strictly "last call".
5. **A5/C4** — priority of the reprompt on an utterance without an address.


---
---

# Round 3 — answers to the review (23. 11. 2026)

## Summary of decisions

| # | Decision | Task |
|---|---|---|
| A5 / C4 | ✅ `ENDED_EARLY` | our team (the account team) **P0**: reprompt on an utterance without an address |
| B7, B8 | ✅ We do not classify the status, we decide by features | — |
| B14 | ✅ The outcome for the caller decides; the tool failed and there is no outcome → `API_ERROR` | — |
| B15 | ✅ The P2 task is only for task 2; we do **not** implement diagnostics in the classifier | — |
| B16 | ✅ What came last before the hangup decides (with the B17 exception, see below) | — |
| B17 | ❓ A choice is needed between your rule and the implicit hazard feature (below) | our team (the account team): refine the classifier once tickets get a hazard feature |
| C1 | ✅ Note in NOTES.md | — |
| C2 | ✅ | — |
| C3 | ✅ (⚠️ one objection about Voltika, below) | — |
| C5 | ✅ Resolver — P0, ASR — P1 of the product team | — |
| C7 | ✅ The classifier labels **every** call; "best outcome + repeat calls" is for the dashboard only | our team (the account team) **P2** |
| C8 | ✅ The ticket comes first; a transfer on hazard is mandatory; with a full queue — offer to wait | our team (the account team) **P0** |

## Clarifications and admission of mistakes

### B16 / C8 — I misread your round 1
In round 1 you wrote: "The fallback on queue_full is decided by my team, task p0, first of all a ticket must be created" (translated from the Russian). I read this as "after `queue_full` create a ticket" (order transfer → ticket). You meant the **order in the flow**: first the ticket, then the transfer. Corrected.
The target flow for a hazardous situation, as I now understand it:
1. Address known → **first** `create_ticket` with "hazard" priority (the ticket gets into the system immediately; reaching a dispatcher takes time).
2. Then a **mandatory** `transfer` to dispatch (per README).
3. Queue full → the bot says so, offers to wait and holds the caller with a retry. Technically `queue_full` means the Voltika queue (limit 10) did **not accept** the call, so "wait" = the bot holds the line and repeats `transfer`, rather than putting the caller in the queue.
4. No address (direct transfer) → first ask for the address (item 3 of C8, round 2).
My "offering a transfer right after queue_full is pointless" I withdraw: with waiting and a retry it makes sense.

### C5 — my round 1 was worded too strongly
You are right: in round 1 the C5 heading was "Address failures = speech recognition". That was an exaggeration based on a single correlation (`asr_conf` before failed attempts). The round 2 check showed 54 % ASR / 46 % resolver. This is the second place where the agent (me) was wrong — also for NOTES.md.

### B14 — how I understood your decision
- The outcome already exists (status reported / ticket / transfer), then `send_sms` or another tool failed → label by the outcome. The caller received the outcome.
- The tool failed, and there is no outcome for the caller → `API_ERROR`.
If you meant that an `send_sms` failure **after** the outcome also gives `API_ERROR`, correct me. Currently it is recorded in the specification as "by the outcome".

### C7 — clarification
I did not propose merging calls in the classifier: deduplication concerned only the dashboard. `predictions.csv` contains all 11,400 calls, each with its own label.

## B17 ❓ Is there a hazardous-ticket feature in the logs — checked

All fields of all night 1 events were checked (11,400 calls + 60 labeled):
- `create_ticket.args`: only `address_id`, `description`; `result`: only `ticket_id`. **There is no priority or category field.**
- `transfer`: only `target`, `status`. `route`: only `target`.
- **There is no explicit "hazardous ticket" feature in the logs.** Currently there is none and there cannot be: hazardous calls on night 1 get no ticket at all.

**But there is an implicit hazard feature, and it is structural:** a `transfer` attempt to dispatch. Per README the bot transfers **only** in a hazardous situation. On night 1 this holds in 1,026 of 1,026 calls: in every call with a `transfer` the bot said "Toto je nebezpečná situácia…", and no call without a `transfer` has this phrase.

⚠️ **Contradiction between B16 and your B17 rule** in your own target flow (ticket → transfer):

| Order in the flow | B16 "last before hangup" | B17 "always `TICKET_CREATED`" |
|---|---|---|
| ticket ok → transfer `queue_full` (your target flow) | `TRANSFER_FAILED` | `TICKET_CREATED` |
| transfer `queue_full` → address → ticket ok (direct transfer without an address, C8 item 3) | `TICKET_CREATED` | `TICKET_CREATED` |

For the caller the outcome is the same in both cases: there is a ticket, there is no dispatcher. But the "last before hangup" rule gives different labels depending on the order of steps in the flow. So for the pair "ticket + failed transfer" a separate rule is needed that does not depend on order:
- **(a) your rule literally:** no explicit flag → `TICKET_CREATED`.
- **(b) my recommendation:** treat the transfer attempt as a hazard feature (it is structural, 1,026/1,026) → by your own condition "hazardous ticket and no dispatcher reached" → `TRANSFER_FAILED`.

Why I recommend (b): your B17 condition "if the hazard can be determined — `TRANSFER_FAILED`" is in fact already satisfiable now. Moreover (b) coincides with B16 for your target order "ticket → transfer". The risk of (b): on night 2 a transfer may appear not only on hazard (e.g. "I want an operator", or a fallback after an API failure), and then the feature becomes noisy.
The remaining combinations (status reported → transfer failed, route → transfer etc.) are decided by B16 — the last before the hangup. A `connected` transfer → always `TRANSFERRED`.

## C3 ⚠️ Objection: I do not recommend hiding it from Voltika
I understand the motive, but:
1. Tickets are created in a system that Voltika dispatch sees. In the 2,052 tickets of night 1 the description is the bot's phrase "Na vašej adrese zatiaľ poruchu neevidujeme. Opíšte mi prosím, čo sa stalo." Dispatchers have most likely already seen it or will see it.
2. If Voltika finds this on its own after our "what happened" email, it will hurt trust more than the bug itself. The email in the assignment is graded on honesty ("úprimný").
3. A soft option: one line in the email — "našli sme aj chybu v popise hlásení, už ju opravujeme a popisy z nedele doplníme" — plus the backfill of the 2,052 tickets. This shows that we are in control of the situation, not just making excuses.
The decision is yours. In TASKS the backfill is currently marked "awaiting decision".

---
---

# Round 4 — answers to the review (23. 11. 2026)

| # | Decision |
|---|---|
| B14 | ✅ The classifier relies on the **known scenario** (`resolve_address`, `get_outage`, `create_ticket`, `transfer`, `route`). New tools **do not affect the label at all** — neither as success nor as failure. This refines round 3: the row "failure of a new tool without an outcome → `API_ERROR`" is withdrawn; such a call is classified by the known events. |
| B17 | ✅ Option **(b)**: "ticket created + transfer failed" → `TRANSFER_FAILED`. The condition "the hazard is visible and works correctly" is verified (below). |
| C3 | ✅ Decision: we fix it silently, we do not tell Voltika about the error in the ticket descriptions (the client did not raise it). Recorded in NOTES.md. |
| C7 | ✅ Deduplication is only a task for task 2, not implemented. |

### B17 — check of the hazard feature
The feature is a `transfer` attempt to dispatch (a structural event). Checked in both directions:

| Night 1 + sample | Has `transfer` | No `transfer` |
|---|---:|---:|
| the caller described a hazard (drôt, kábel, iskrí, horí, strom, stĺp…) and the bot said "nebezpečná situácia" | 1,026 + 8 | **0** |
| neither hazard words nor the bot phrase | **0** | 10,374 + 52 |

No false positives: every transfer is a hazardous situation. No misses either: not a single hazardous situation without a transfer. The classifier uses only the `transfer` event; the caller's text is not needed.
Limitation: checked only on night 1. If on night 2 a transfer appears not because of a hazard (e.g. "I want an operator"), the feature becomes noisy. For this TASKS already has a task: refine the classifier once tickets get an explicit hazard flag.


---
---

# Round 5 — independent review of the specification and decision (23. 11. 2026)

The review was done by a separate agent (Opus, high). It built a prototype strictly per §4: 60/60 on the sample, the night 1 distribution exactly matches §8. The reviewer's synthetic data: 26 scenarios. Checks following the review — `python scripts/profile_night.py`, section `ROUND 5`.

| # | Review finding | Decision |
|---|---|---|
| R1 | B17: "ticket + failed transfer in any order" also triggered on a repeated transfer `connected` | ✅ A wording error in the base case (found by you). Fixed: the **last** transfer is not `connected` |
| R2 | Several `hangup`s in one call | ✅ Impossible: the caller will not return to the same call. In the data there is exactly 1 `hangup` for each of the 11,400 calls. In the specification: the end of the call = the first `hangup`, everything after is a log artifact |
| R3 | Unclear which call a result belongs to | ✅ There is no ambiguity: the bot is sequential and always waits for the tool's response (0 calls before the answer to the previous one). The wording is kept, an explanation added |
| R4 | `outage_id` renamed in the response | Not discussed → **not implemented** (B14: we do not adapt to the unknown). Instead you raised the question of validating `outage_id` itself, see below |
| R5 | The ADDRESS condition "the call was ended by the bot" does not account for `system` | ✅ `by ∈ {bot, system}`, as in B13. The second part of the proposal (take into account any new call after the address) not accepted — B14 |
| R6 | A `get_outage` timeout → `route` gave `OUT_OF_SCOPE` (because of the order of steps) | ✅ `route` → `OUT_OF_SCOPE` only if there was no unrecovered failure before it; otherwise the failure decides (`API_ERROR`) |
| R7 | The caller hung up without waiting to be connected to the dispatcher | ✅ **`ENDED_EARLY`** (your decision). This is not A1: A1 is waiting for a tool's response, here it is waiting for a connection to a human. A late `transfer` after the `hangup` does not change the label |
| S04 | A direct transfer on hazard failed → address → status reported / ticket created | ✅ `TRANSFER_FAILED`: there was a transfer attempt, and the last transfer is not `connected` — regardless of what came after |
| §5.1 | Non-ok status + `outage_id: null` | ✅ Currently "no outage" = status `ok` and `{"outage_id": null}` (2,639 responses). With a non-ok status `null` means "no outage" only if the bot went on (asked for a description / created a ticket). Otherwise — a failure → `API_ERROR` |
| minor | the bot utterance "right after" the result (skip caller utterances and unknown events), equal `t` → file order, case of `ok`/`connected`, `result` not a dict, BOM (`utf-8-sig`), an event without `t` → the previous `t`, §4 is the normative section | ✅ Incorporated as wording clarifications. A transfer to another `target` with status `connected` stays `TRANSFERRED`: if the label were tied to the target name, renaming the target on night 2 would break all transfers |
| §6 | byte-level stdout check, regression on §8, synthetic S01–S25, run with `python -I`, summary of new values in stderr | ✅ Added to the definition of done |

## `outage_id` check — a new finding (P0)
The question was: can the bot, with the current architecture, verify `outage_id`? **It cannot.** The bot has three tools, `get_outage(address_id)` returns only `outage_id` and `eta`. There is nothing to request data by `outage_id` or to cross-check it against the address — the bot fully trusts the OMS.
A quick check (`ROUND 5`) showed that the OMS responses contradict themselves:
- the same `address_id`, a repeat request within 5 min → a different `outage_id` in 745/819 cases (91 %); "outage exists" ↔ "no outage" in 346/819 (42 %);
- the same `outage_id`, calls within 10 min → a different ETA in 825/1,016 (81 %);
- 965 of 996 `outage_id`s occur in several towns.

Caveat: the data is fictional, this may be a generation artifact. A separate agent (Opus, medium) is assembling a document with evidence for manual verification and checking alternative explanations: [outage_consistency_evidence.md](outage_consistency_evidence.md). The tasks are in `TASKS_02-04.md`, P0.

---
---

# Round 6 — review of the `classify.py` code and decisions (23. 11. 2026)

The code review was done by a separate agent (Opus). Its verdict: "ready after fixes". Night 1 is correct: 60/60, distribution = §8, stdout matches the file byte for byte.

| # | Finding / question | Decision |
|---|---|---|
| K1 | `route` after a failed `create_ticket` gave `OUT_OF_SCOPE` (the code checked only `get_outage`) | ✅ Fix: R6 first checks the furthest stage → `API_ERROR` |
| K2 | Shuffled input with equal `t` broke "the bot spoke right after the result" (1,484 calls of night 1 after shuffling) | ✅ For unordered input sort by (`t`, event rank) |
| K3 | An event without `type` with only `text` remained unknown | ✅ → `bot` |
| K4–K7 | `--out` was clobbered on invalid input; a lone `\r` split a line; `call_id` from a broken line was not decoded; `outage_id: false` was counted as an outage | ✅ Fix |
| K8 | Tests: `test_A4` did not model A4, three tests only checked "label from the list", tests for K1–K7 were missing | ✅ Fix and extend |
| D1 | A ticket on a **known** outage | ✅ A ticket must not be created on a known outage. If there is one anyway, we do not count it as the outcome; the reported status decides (`KNOWN_OUTAGE_INFORMED`). README: `TICKET_CREATED` — "porucha nebola známa" |
| D2 | A ticket created **after** the caller left (the future P2 from B2) | ✅ `TICKET_CREATED`: the ticket exists in the system (B3 logic) |
| — | Night 2 risks from the code review (new success synonyms like `answered`, millisecond time shifts, renamed types/tools) | ❌ Not taken into account now (your decision) |

Specification — rev. 6.

## Note on the repository (appended)

`labeled_sample.md` and `calls_address_rejected.md` referenced above are full call transcripts, so they are not committed; regenerate them with `scripts/render_labeled.py` and `scripts/render_calls.py`.
