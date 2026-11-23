# Fix backlog — who owns what, priorities, order, SMS, switch-off

Detailed version of the short answers in [`TASKS_02-04.md`](../TASKS_02-04.md). Item ids (A1, C8, R6, …) refer to the decision log [contested_cases.md](contested_cases.md). Numbers come from the scripts named in each linked document.

Priorities P0–P2 apply to our team (the account team) and the product team. Voltika gets no priorities.

## 1. Who owns which fix

### Us — the account team (bot flow on the Voltika account)
- **P0** — **Inconsistent `get_outage` answers.** The same address re-queried within ≤ 5 min gets a different `outage_id` in 91 % of cases, and flips between "known outage" and "no outage" in 42 %. The ETA for one outage differs within 10 min in 81 %. Evidence: [outage_consistency_evidence.md](outage_consistency_evidence.md); act on it only after a human has reviewed that document. (round 5)
  - Send Voltika the evidence (examples by `call_id`, time, OMS answer, what the caller heard) and ask for an explanation.
  - Do not launch ETA SMS until this is resolved: an SMS would put contradictory information in writing.
- **P0** — Bot fallback when `get_outage` fails or times out, instead of "zavolajte neskôr" (call back later). (C6)
- **P0** — Dangerous situations (updated in round 3):
  - **first** a ticket with priority "danger" (address known), with the number read out to the caller;
  - **then, always**, a transfer to dispatch;
  - on `queue_full`/`timeout` the bot says the queue is full, offers to wait, and keeps the caller on the line while it retries the transfer;
  - without an address (direct transfer, 114 of 228 calls) the bot asks for it first;
  - the bot distinguishes regular tickets from danger tickets. (A3, C8)
- **P0** — Re-prompt when the caller says something that is not an address ("haló", "počujete ma"): 274 calls got no reaction from the bot. (A5/C4)
- **P0** — Send the caller's own description in `create_ticket.description`, not the bot's prompt. Today 2,112 of 2,112 tickets have no real description. (C3)
  - Decision (round 4): fix it quietly and do not tell Voltika. Back-fill the descriptions of the 2,052 night-1 tickets from the transcripts only if that can be done with no visible consequences for the client.
- **P1** — The bot does not go silent while it waits for `get_outage`; it tells the caller that it is checking. (A1)
- **P1** — Stale-ETA check: never say a time that has already passed, neither in the call nor in an SMS. Say instead that the outage is registered and no current estimate is available yet. (C2, 377 calls)
- **P2** — For an unknown outage, create a ticket even if the caller hangs up before `create_ticket` (needed for SMS). (B2)
- **P2** — Classifier: separate diagnostics for broken log lines (`--diagnostics`). `predictions.csv` keeps one of the 8 labels. (B15)
- **P2** — Dashboard (updated in round 3): take the **best outcome** per caller and show a repeat-call metric. The classifier still labels every call separately, without merging. (C7: a "last call only" rule would hide 703 failed calls and count 51 people who were helped earlier as failures.)
  - *Caution (round 5):* repeat callers never gave the same address twice (367/367), and in 332 cases the addresses were in different towns ([outage_consistency_evidence.md](outage_consistency_evidence.md), section G). Repeat-call numbers are unreliable because a `caller_hash` may not be one person with one problem. Don't show them to the client without checking.
- *No priority set* — Once tickets carry an explicit "danger/regular" flag, update the classifier: a danger ticket without a transfer accepted by dispatch → `TRANSFER_FAILED`. Today the transfer attempt itself is the danger marker (error-free on night 1). (B17)

### Product team
- **P0** — The bot cannot check a `get_outage` answer. Nothing in the architecture lets it look up an `outage_id` or match it to the address; the bot trusts OMS blindly. (round 5)
  - Extend the integration: once Voltika provides it, request the outage area/addresses and the last-update time from OMS, and add a lookup tool by `outage_id`.
  - Basic checks before the answer is read out: the ETA is in the future, the `outage_id` matches the address, and the answer agrees with recent answers for the same address.
  - Store the raw OMS response for audit.
- **P0** — Resolver: it does not understand town parts (Grinava, Cajla, Kráľová, Harmónia: 50–57 % of attempts fail) and substitutes a street with the same name in another town (the 60 A2 calls). About 209 calls affected. (C5, accepted in round 3)
- **P1** — Speech recognition: for `no_match`/`ambiguous` the mean `asr_conf` is ≈ 0.6, for successful attempts it is ≥ 0.7. About 247 of 456 address failures affected. (C5, accepted in round 3)
- `create_ticket` accepts the bot's prompt as a description and confirms the ticket — add validation. (C3)
- `create_ticket` reliability: 60 timeouts, 54 of them in the 21:40–22:30 window ([task2_failures_by_cause.md](task2_failures_by_cause.md)).

### Voltika
- Explain and fix the inconsistent OMS answers: different `outage_id`s for one address and "known ↔ none" flips within minutes, and different ETAs for one outage. Provide an API with outage area/addresses and last-update time. (round 5)
- Fix stale ETAs in OMS: they lag by up to 2 h, median 43 min. (C2)
- `get_outage` API degradation ≈ 21:40–22:35 local time (533 of 592 timeouts). Load-test and scale OMS for a storm peak of ≈ 2,600 calls/h. (C6)
- Discuss: "danger" priority in the dispatch queue (limit 10), with danger tickets and transfers moved up the queue. (C8)
- Question: does the address registry they supply contain town parts? (C5)

## 2. Order — "what so it does not happen again, and in what order"
Principle: safety first, then the largest failure groups, then what we can ship ourselves fastest. Numbers from [task2_failures_by_cause.md](task2_failures_by_cause.md).
1. **Before the next storm — us** (flow changes on the account; we depend only on ourselves):
   1. Dangerous situations: danger ticket, then transfer, then waiting when the queue is full. That is 228 calls. It comes first despite the smaller volume, because today the bot tells people with a fallen wire "zavolajte o chvíľu" (call again in a moment).
   2. Fallback for `get_outage` / `create_ticket` failures: 684 calls = 50 % of all failures.
   3. Re-prompt on "haló" (274 calls); the caller's description in the ticket (2,112 tickets).
   4. P1: no silence while waiting; stale-ETA check (377 calls).
2. **Start with Voltika right away.** They have the longest lead time and the root cause no. 1: 90 % of `get_outage` failures fell into the OMS degradation window (21:40–22:30). Needed: an OMS load test and scaling for the ≈ 2,600 calls/h peak. Also: danger priority in the dispatch queue (limit 10), stale ETAs, and an analysis of the inconsistent answers (after a human has reviewed [outage_consistency_evidence.md](outage_consistency_evidence.md)).
3. **In parallel — the product team** (weeks): resolver town parts (P0, ≈ 209 calls), `get_outage` answer checks (P0), ASR (P1, ≈ 247), `create_ticket` validation.
4. **Measurement** (proposal; priority is your call):
   - compute the client dashboard by call outcome ("helped / failed by cause", which `classify.py` already gives) instead of `ended_by`; proposed to move up from P2 to P1;
   - run `classify.py` after every night as a regression check.
5. **SMS last**: only after the ETA check (P1) and after the OMS inconsistency is explained (P0). Otherwise an SMS will carry a stale or contradictory time.

## 3. SMS "from next week"
Answer: **"Yes, but not blindly from Monday."** We give a date after the client answers our questions and after the ETA check. The questions are in the email (task 3).
- **Why we don't promise "next week".** 377 calls that night were given an ETA that had already passed, and OMS answers for the same address contradict each other ([outage_consistency_evidence.md](outage_consistency_evidence.md)). An SMS would put the error in writing and trigger repeat calls.
- **The scope depends on the client's answers:**
  - who gets the SMS: only the callers, or proactively everyone at an address with an outage (that needs numbers and consent, which only Voltika has; consent is a GDPR question);
  - whether to send a new SMS when the ETA changes and when power is restored;
  - what to send when the ETA is unknown.
- **Proposed phases:**
  - Phase 1: SMS only to callers, and only with a current ETA. Depends on the ETA check (P1) and on ticket-on-hang-up (P2).
  - Phase 2: updates and proactive SMS, after Voltika decides on numbers and consent and after OMS is fixed (P0).

## 4. Should Voltika switch the bot off? — No: fix it, don't switch it off
Details: [task4_switch_off.md](task4_switch_off.md); reproduce with `python scripts/task4_capacity.py`.
- **Capacity vs demand.** 3 night operators × 60/4 min = **45 calls/h**. Demand by hour was 1,200–2,600/h, with the peak of 2,600/h at 21:00, which is **57.8×** capacity. Demand exceeded capacity in all 6 hours.
- **Without the bot**, operators could have taken at most 270 of 11,400 calls (2.4 %), leaving 11,130 unanswered. In the peak hour that is 45 of 2,600.
- **With the bot (as on 15. 11.)**, 8,778 of 11,400 callers were helped (77.0 %), 32.5× the operators' maximum. Failures were 1,368 (12.0 %).
- **In the worst window** (OMS degradation 21:40–22:30, 32.8 % failures) the bot still helped 1,095 callers. Operators could have taken 38 in the same 50 minutes.
- **Replacing the bot** would take ≈ 173 night operators (2,600 / 15 per operator at the peak), not 3.
- **With fallbacks.** Adding a fallback for tool failures (684 calls) would raise help to at most 83.0 %. This is an upper bound and an assumption.
- **Caveats.** 4 min/call at 100 % utilisation is an upper bound for the operators. There is no model of abandonment or repeat calls. Connected transfers to dispatch were 96–171/h, more than 3 operators can take at 4 min each, so dispatch has different staffing or shorter calls. This does not change the conclusion: even triple capacity covers 5.2 % of the peak.
