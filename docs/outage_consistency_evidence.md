# Consistency of `get_outage` responses (night of 15.11.2026): evidence base

## In brief

- **Claim:** within minutes, OMS (`get_outage`) returns different `outage_id`s for the same `address_id`, flips between "outage known" and "no outage", the ETA jumps around for one `outage_id`, and a single `outage_id` shows up in different towns.
- **Verdict: the numbers are confirmed** (independent code; a 1–2 pair discrepancy due to a different timestamp). **All "legitimate" explanations are refuted** by the data: restoration/new outage, ETA update, one outage covering many villages, ambiguous `address_id`, OMS degradation.
- **But:** the responses are statistically **indistinguishable from random**. If all responses are shuffled between all requests, the same percentages come out (section H). There is no structure at all (neighbours, persistence, time of night) in the responses.
- **Confidence:** high that the responses in the data are inconsistent; **low** that this is a real OMS bug rather than an artefact of how the fictional dataset was generated (repeat callers show the same picture: a different address in a different town every time).
- **Main caveat:** telling the client "your OMS returns random data" on the basis of this data alone is not possible. OMS logs are needed (see the last section).

## How to reproduce

```
python scripts/check_outage_consistency.py
```

Stdlib only, deterministic (shuffling with the fixed seed 20261115), ~1 s. An optional argument is the path to the data folder (default `data/`). All numbers below come from the output of this command; the section letter matches the section of the output.

Definitions:
- **Response** = a `tool_result` of `get_outage` with `status: ok` (8,827 of them; 592 timeouts are not counted). Known outage = `outage_id` is not `null` (6,201), no outage = `null` (2,626).
- **Response time** = `calls.csv started_at` (UTC) + `t` of the `tool_result` event; in this document it is local time (UTC+1).
- **Pair** = two *consecutive in time* responses for the same `address_id`, with at most N minutes between them.
- **"Told to the caller"** = the event following the response is a bot utterance (not a `hangup`); the caller did not hear 273 responses.
- City = the text after the comma in the bot utterance "Overím si: <street> <no.>, <city>."; parts ("Pezinok – Cajla") are merged into the city.

Difference from the original check (`profile_night.py`, ROUND 5): there, time = call start; here it is the moment of the response. Hence 817 pairs instead of 819, 744 instead of 745, 347 instead of 346. The other numbers match.

## Summary tables

### B. One `address_id`, consecutive responses

| Window | Pairs | Different response | Flip "yes ↔ no" | Both "yes", but different `outage_id` |
|---|---|---|---|---|
| ≤ 2 min | 340 | 307/340 (90.3 %) | 134/340 (39.4 %) | 173/173 (100 %) |
| ≤ 5 min | 817 | 744/817 (91.1 %) | 347/817 (42.5 %) | 397/397 (100 %) |
| ≤ 15 min | 2,108 | 1,919/2,108 (91.0 %) | 879/2,108 (41.7 %) | 1,040/1,042 (99.8 %) |
| ≤ 60 min | 5,313 | 4,836/5,313 (91.0 %) | 2,237/5,313 (42.1 %) | 2,599/2,603 (99.8 %) |

The share does not depend on the window (2 min ≈ 60 min). This is the first sign that time is not the cause.

- Addresses with ≥ 2 responses: 1,338; of them, those that got ≥ 2 different responses over the night: 1,320/1,338 (98.7 %).
- If both responses are "outage exists", the `outage_id` matched in only 4 of 2,603 pairs within 60 min.
- Over the whole night: the 6,201 "outage exists" responses fall on 6,185 distinct (outage_id, address) pairs. The same `outage_id` almost never repeats for the same address.

### D. ETA for one `outage_id`

| Metric | Value |
|---|---|
| Consecutive responses ≤ 10 min, ETA different | 825/1,016 (81.2 %); later 398, earlier 427 |
| `outage_id`s with ≥ 3 responses, ETA monotonic over the night | 73/938 (7.8 %) |
| Set of ETA values (local) | only 23:00, 00:00, 01:00, 02:00 (1,936, twice as frequent), 03:00, 04:00 |
| "Outage exists" responses where the ETA is already in the past at the moment of the response | 377/6,201 (6.1 %) |

### E. Geography of `outage_id`

| Metric | Value |
|---|---|
| Distinct `outage_id`s | 996, the numbers densely fill O‑5000…O‑5999 |
| `outage_id` in > 1 town | 965/996 (96.9 %) |
| Towns per `outage_id` (distribution) | 1: 31, 2: 63, 3: 149, 4: 249, 5: 214, 6: 166, 7: 94, 8: 28, 9: 1, 10: 1 |
| `outage_id` simultaneously in Malacky and in Šamorín (~50 km as the crow flies, on opposite sides of Bratislava) | 186 |
| Total towns in the data | 10 |

### F. OMS degradation window (21:40–22:35 local) and by hour

| Pairs ≤ 5 min | Pairs | Different response | Flip | Both "yes", different id |
|---|---|---|---|---|
| Both responses inside the window | 116 | 105/116 (90.5 %) | 52/116 (44.8 %) | 53/53 |
| Both responses outside the window | 683 | 623/683 (91.2 %) | 290/683 (42.5 %) | 333/333 |

By hour (hour of the second response): 19 h 93.8 %, 20 h 90.3 %, 21 h 91.0 %, 22 h 89.3 %, 23 h 93.4 %, 00 h 90.0 % different responses. The share of "outage exists" among all responses is stable all evening: 69.4 / 70.1 / 71.0 / 69.6 / 70.2 / 71.2 %.

### G. People

| Metric | Value |
|---|---|
| The same `caller_hash`, the same address, ≥ 2 heard responses | **0** |
| `caller_hash`es with ≥ 2 responses in different calls | 367; not once did they give the same address twice: 367/367; addresses in ≥ 2 different towns: 332 |
| Addresses where ≥ 2 **different** people heard a response | 1,333 (8,091 calls) |
| …of these, at the same address some heard "outage exists", others "no outage" | 1,097/1,333 (82.3 %), 7,231 calls |
| …two different ETAs | 1,167/1,333 (87.5 %) |
| …either of the two | 1,303/1,333 (97.7 %), 8,027 calls |

### G2. Structure

| Test | Result | What to expect from a real OMS |
|---|---|---|
| P("yes" \| previous response for the address "yes") | 3,462/4,938 (70.1 %) | close to 100 % within minutes |
| P("yes" \| previous "no") | 1,468/2,082 (70.5 %) | noticeably lower |
| Unconditional share of "yes" | 70.3 % | — |
| Two different addresses on the same street in the same town, both "yes", ≤ 15 min: the same `outage_id` | 28/20,101 (0.1 %) | most (neighbours on one line) |
| Addresses with ≥ 8 responses where all responses are of one kind | 10 out of 438; with independent responses ~17.8 would be expected | many more |

### H. Random baseline (responses shuffled between all requests, 20 times)

| Metric | Observed | Shuffled, min…max |
|---|---|---|
| ≤ 5 min, same address: different response | 91.1 % | 88.7…92.9 % |
| ≤ 5 min: flip "yes ↔ no" | 42.5 % | 38.4…44.8 % |
| ≤ 5 min, both "yes": different `outage_id` | 100 % | 99.5…100 % |
| `outage_id` in > 1 town | 96.9 % | 96.7…97.4 % |
| Average number of towns per `outage_id` | 4.59 | 4.57…4.67 |

The observed values lie within the range of a fully random model. That is, **there is no link at all between address/time and the response in the data**.

## Specific cases for manual checking

Search `data/transcripts.jsonl` by `call_id`. Time is local (the moment of the `get_outage` response). Bot quotes are verbatim: the utterance immediately following the response.

**1. One address, one second, two different outages and two ETAs.** `A-000597`, "Overím si: Kollárova 49, Modra."
- `c-n1-009194`, 23:28:45, `O-5505`, ETA 23:00, caller `91fdf388219a`: "Na vašej adrese evidujeme poruchu. Elektrinu by ste mali mať späť o jedenástej večer." (ETA 23:00 was spoken at 23:28, already in the past.)
- `c-n1-009202`, 23:28:45, `O-5612`, ETA 00:00, caller `ab14e7c1ac35`: "… mali mať späť okolo polnoci."

**2. 4 seconds, different outages.** `A-002021`, "Školská 5, Bernolákovo."
- `c-n1-003895`, 21:17:22, `O-5102`, ETA 03:00: "… okolo tretej ráno."
- `c-n1-003898`, 21:17:26, `O-5821`, ETA 00:00: "… okolo polnoci."

**3. 5 seconds, different outages.** `A-002543`, "Hlavná 34, Limbach."
- `c-n1-001621`, 20:13:51, `O-5765`, ETA 02:00: "… okolo druhej hodiny v noci."
- `c-n1-001623`, 20:13:56, `O-5172`, ETA 23:00: "… o jedenástej večer."

**4. "Outage exists" → "no outage" in the same second, before the ETA.** `A-001950`, "Poľná 28, Bernolákovo."
- `c-n1-009976`, 23:53:27, `O-5956`, ETA 02:00: "Na vašej adrese evidujeme poruchu. … okolo druhej hodiny v noci."
- `c-n1-009977`, 23:53:27, `null`: "Na vašej adrese zatiaľ poruchu neevidujeme. Opíšte mi prosím, čo sa stalo."

**5. The same after 6 s, inside the degradation window.** `A-002579`, "Kollárova 31, Limbach."
- `c-n1-005104`, 21:44:45, `O-5732`, ETA 02:00 (latency 6,760 ms): "… evidujeme poruchu … okolo druhej hodiny v noci."
- `c-n1-005108`, 21:44:50, `null` (latency 7,338 ms): "… zatiaľ poruchu neevidujeme …"

**6. The same after 8 s.** `A-001971`, "Mlynská 28, Bernolákovo."
- `c-n1-003933`, 21:18:05, `O-5436`, ETA 02:00 → `c-n1-003938`, 21:18:14, `null`.

**7. One address, 16 different people in one evening.** `A-002520`, "Hviezdoslavova 26, Limbach." 13 times "outage exists" with 13 *different* `outage_id`s (O‑5932, O‑5019, O‑5227, O‑5857, O‑5553, O‑5183, O‑5775, O‑5470, O‑5838, O‑5666, O‑5103, O‑5391, O‑5431) and ETAs from 23:00 to 04:00, 3 times "no outage". For example: `c-n1-002342` 20:35:18 → ETA 04:00, `c-n1-002377` 20:36:16 (a minute later) → ETA 23:00; `c-n1-003993` 21:19:45 → `O-5553`, ETA 00:00, `c-n1-004054` 21:20:31 → "zatiaľ poruchu neevidujeme".

**8. One `outage_id` in distant towns.** `O-5001` is in 4 towns:
- `c-n1-003098`, 20:57:15, "Športová 35, Limbach.", ETA 04:00
- `c-n1-009527`, 23:39:12, "Kollárova 16, Malacky.", ETA 04:00
- `c-n1-010241`, 00:02:32, "Družstevná 37, Svätý Jur.", ETA 02:00
- `c-n1-011074`, 00:44:05, "Mlynská 57, Šamorín.", ETA 01:00

**9. One `outage_id` in 6 towns, different ETAs.** `O-5004`: Bernolákovo (`c-n1-001841`, ETA 01:00), Pezinok (`c-n1-003350` and `c-n1-003752`: Krátka 6 and Krátka 3, ETA 23:00), Limbach (`c-n1-004897`, ETA 02:00), Šamorín (`c-n1-006486`, 22:17:11, ETA 00:00) and **7 seconds later** Malacky (`c-n1-006490`, 22:17:18, ETA 02:00), Ivanka pri Dunaji (`c-n1-009326`), Malacky again (`c-n1-009344`, ETA 04:00).

**10. The ETA of one outage back and forth.** `O-5017`: `c-n1-007009` 22:29:37 Senec → 04:00; `c-n1-007273` 22:36:04 Malacky → 02:00; `c-n1-007457` 22:40:14 Šamorín → 04:00. `O-5033`: 19:58:41 → 02:00, 20:04:59 → 01:00, 20:13:02 → 02:00.

**One and the same person with contradictory responses: there are no such cases.** Repeat callers (`caller_hash`) name a *different* address every time, usually in a different town. Example: `4d4ecf93e3b5` called 7 times in one evening with 7 addresses in Ivanka pri Dunaji, Senec, Malacky, Limbach, Modra (×2), Limbach (`c-n1-000108` … `c-n1-008459`); `f3c515ded2e1`: 7 addresses in Modra, Senec (×2), Svätý Jur, Malacky (×2), Modra. The contradictions are heard by **different people at the same address** (section G: 1,097 addresses, 7,231 calls).

Checked by hand against the raw jsonl and `calls.csv`: cases 1, 5 and 8 (`c-n1-009194`, `c-n1-009202`, `c-n1-005104`, `c-n1-005108`, `c-n1-003098`, `c-n1-011074`): the `address_id` in args, the "Overím si" utterance, `outage_id`/`eta`, and time = `started_at` + `t` all match.

## Alternative explanations

### 1. The outage was restored / a new one started between requests
**Test:** share of discrepancies depending on the interval; for "yes → no" pairs, whether the second request came before the ETA of the first response; the pattern X → other → X at an address within 15 min.
**Result:** the discrepancy is 90 % already at ≤ 2 min and does not grow towards 60 min; the median interval in differing pairs ≤ 5 min is 149 s, 139 pairs are ≤ 60 s, and there are pairs with a 0 s difference. "Yes → no" happens before the promised ETA in 168/179 (93.9 %) of cases. With restoration, "no → yes" right after "yes → no" would be rare, but here there are 168 of those against 179 in the opposite direction. A return to the same `outage_id` (X → Y → X): 0 out of 321 triples.
**Does it explain it?** No.

### 2. The ETA was legitimately updated during the night
**Test:** direction of change between consecutive responses for one `outage_id`; monotonicity of the ETA over the night.
**Result:** changes later 398 and earlier 427 are symmetric, like noise; monotonic sequences 7.8 %. The ETA is sometimes already in the past at the moment of the response (6.1 %). The values are only 6 round hours.
**Does it explain it?** No.

### 3. One outage covers several villages
**Test:** number of towns and addresses per `outage_id`; match of `outage_id` between neighbours on one street.
**Result:** 96.9 % of ids have several towns, including 186 ids simultaneously in Malacky and Šamorín; almost every response for an id is a different address. Neighbours on one street get the same id within 15 min in 0.1 % of pairs. A widespread outage would produce *many* addresses with one id and the *same* id for neighbours; here it is the opposite.
**Does it explain it?** No (a large outage does not explain why the same address gets a different id a second later).

### 4. `address_id` does not identify a single address
**Test:** the set of "Overím si: …" texts per `address_id` and vice versa.
**Result:** strictly 1 : 1 for all 1,807 addresses. The bot read to the caller exactly the address that went into `get_outage`.
**Does it explain it?** No.

### 5. Link to the OMS degradation (21:40–22:35)
**Test:** share of discrepancies inside and outside the window, by hour.
**Result:** 90.5 % inside against 91.2 % outside; by hour 89–94 %. The share of "outage exists" is ~70 % all evening.
**Does it explain it?** No. The inconsistency is not a consequence of load; the degradation is a separate problem (timeouts).

### 6. The same person received contradictory responses
**Test:** `caller_hash` + `address_id`, only heard responses.
**Result:** 0 such people; repeat callers never named the same address. There is a human effect, but it works through *different* people at the same address (neighbours/family members): 97.7 % of addresses with ≥ 2 heard responses received a contradiction (8,027 calls).
**Does it explain it?** Not applicable as an explanation; the impact estimate is in section G.

### 7. Generation artefact (fictional dataset)
**Test:** shuffling of responses between all requests (H); persistence of the response (G2); behaviour of repeat callers.
**What would look the same if `outage_id`/ETA were generated randomly and independently of address and time:** all percentages in sections B, D, E (they match the shuffled model); the ids densely fill the range O‑5000…O‑5999 (996 of 1,000; with 6,201 uniformly random draws from 1,000 ids, ≈ 998 would be expected: 1,000·(1 − e^−6.2)); P("yes") = 70 % regardless of the previous response and the hour; ETA from 6 round values, 02:00 twice as frequent. Plus, independently of OMS, the `caller_hash` of repeat calls is just as "random" with respect to the address, which suggests that the generator assigns attributes independently in general.
**Does it explain it?** **Not ruled out, and the most economical.** The data do not allow distinguishing "OMS returns garbage" from "the dataset generator did not model consistency". I note that the README says the situation is "modelled on what really happens in production", so a deliberately included defect of this kind is also possible; the data do not settle this.

## What this proves and what it does not

**Proves (within the data):**
- The `get_outage` responses in the bot logs are inconsistent by address, by time and by outage; there are 1,097 addresses where some callers heard "outage exists" and others "no outage".
- The bot passed the response through as is (the address in args matches what was read to the caller; the utterance corresponds to the response), i.e. our flow does not introduce the contradictions, it relays them. The bot has no tool to verify an `outage_id`.
- This is explained neither by restoration, nor by ETA updates, nor by a widespread outage, nor by OMS degradation, nor by an ambiguous `address_id`.

**Does not prove:**
- That the real Voltika OMS behaves like this. We see only what is recorded in our transcripts; if the record is correct, the problem is on the OMS/integration side, but a data artefact is equally likely.
- That no response was correct: we have no "ground truth" about the outages.

**What we need from Voltika to confirm:**
- Server-side `get_outage` logs for 15.11 19:00–01:00 (request id / time, `address_id`, response), to compare against our transcripts for the pairs from cases 1–6.
- For `O-5001`, `O-5004`, `O-5017`: the outage zone (feeder/transformer, list of addresses), creation/closure time, and the history of ETA changes with `last_updated` timestamps.
- For `A-000597`, `A-002520`, `A-001950`: which outages were really at these addresses that night.
- A description of the OMS logic: how the `outage_id` is chosen when an address has several records; whether there is a cache/load balancer with several replicas (replica desync would give a similar picture, but then the same id would be returned at least sometimes, whereas we have X → Y → X 0 times).
