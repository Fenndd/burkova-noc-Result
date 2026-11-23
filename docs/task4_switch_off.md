# Task 4, item 3: should the bot be switched off?

Working document for the reviewer (English). All numbers are printed by `python scripts/task4_capacity.py`. Times are local (Europe/Bratislava, UTC+1). Call labels come from `predictions_night1.csv` (`classify.py`).

## Summary

**Verdict: no, do not switch the bot off. Fix it, do not disable it.** Conditional variant: switching off would make sense only if Voltika had a plan for night-time staffing for this peak, which is not in the data.

- Night operators' capacity: 3 × 60/4 = **45 calls/h**. Peak demand (21:00–21:59): **2,600/h = 57.8× the capacity**; in each of the 6 hours demand exceeds capacity by 27–58 times.
- Without the bot, operators would have taken at most **270 of 11,400 = 2.4 %** of calls over the night; 11,130 (97.6 %) would have been left without help. In the peak hour 45 of 2,600 (1.7 %).
- With the bot, **8,778 / 11,400 = 77.0 %** got help (outage status + ticket + transfer), in the peak hour 1,818 / 2,600 = 69.9 %. That is 32.5 times the operators' maximum.
- The bot failed **1,368 / 11,400 = 12.0 %** (in the OMS degradation window 21:40–22:30: **703 / 2,145 = 32.8 %**), and another 912 (8.0 %) left on their own before getting help. This is a real problem, but even in the window the bot helped 1,095 calls versus 38 for the operators over the same 50 minutes.
- Upper bound if tool failures are fixed (an assumption, not data): the 684 `API_ERROR` calls would get help, then 9,462 / 11,400 = 83.0 %, failures 6.0 %.

## How to reproduce

```
python scripts/task4_capacity.py
```

No arguments, deterministic (two runs give identical output), stdlib only. Reads `data/calls.csv`, `data/transcripts.jsonl`, `predictions_night1.csv`. The definitions of "helped" / "failure" are as in `docs/task2_failures_by_cause.md`.

## 1. Operator capacity

Assumption: 100 % utilisation, no breaks, every call exactly N minutes.

| Minutes per call | 3 night operators, calls/h | over 6 h (19:00–01:00) |
|---:|---:|---:|
| 3 | 60 | 360 |
| **4** | **45** | **270** |
| 5 | 36 | 216 |
| 6 | 30 | 180 |

In the daytime 12 × 60/4 = 180 calls/h (for comparison; the night peak is still 14.4× higher).
The conclusion is robust to the assumption: even at 3 minutes per call (60/h) the peak of 2,600/h exceeds capacity 43 times.

## 2. Demand, capacity and bot outcome by hour

| Hour (local) | Demand | Capacity | Demand/cap. | Not served without the bot | Bot helped | Bot failed | Left on their own (`ENDED_EARLY`) | Helped/cap. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 19:00 | 1,200 | 45 | 26.7× | 1,155 | 996 | 91 | 65 | 22.1× |
| 20:00 | 2,000 | 45 | 44.4× | 1,955 | 1,661 | 141 | 133 | 36.9× |
| **21:00** | **2,600** | 45 | **57.8×** | 2,555 | 1,818 | 434 | 265 | 40.4× |
| 22:00 | 2,500 | 45 | 55.6× | 2,455 | 1,700 | 488 | 245 | 37.8× |
| 23:00 | 1,900 | 45 | 42.2× | 1,855 | 1,594 | 131 | 128 | 35.4× |
| 00:00 | 1,200 | 45 | 26.7× | 1,155 | 1,009 | 83 | 76 | 22.4× |
| **Total** | **11,400** | 270 | | **11,130 (97.6 %)** | **8,778 (77.0 %)** | **1,368 (12.0 %)** | **912 (8.0 %)** | |

The remainder up to 11,400 is 342 `OUT_OF_SCOPE` calls (the bot answered that the question is off-topic; I count them neither as help nor as failure). Peak over 15 minutes: 21:30, 671 calls (rate 2,684/h; capacity over 15 minutes 11.2).

## 3. Scenarios

| Scenario | Help over the night | In the peak hour (2,600) | Caveat |
|---|---:|---:|---|
| (a) bot off, operators only | ≤ 270 / 11,400 = **2.4 %** | ≤ 45 = **1.7 %** | upper estimate: no queue build-up and no abandonment, 100 % utilisation |
| (b) bot as on 15.11. | 8,778 / 11,400 = **77.0 %** | 1,818 = **69.9 %** | fact; 7,980 resolved by the bot itself, 798 handed to dispatchers |
| (c) bot + `get_outage`/`create_ticket` failures fixed | ≤ 9,462 / 11,400 = **83.0 %** | ≤ 2,091 = **80.4 %** | **upper bound, assumption**: all 684 `API_ERROR` calls would get help; addresses (456) and transfer (228) do not change |

In (c) 684 failures remain (6.0 %). This is not a forecast of the effect of planned fallbacks, but a ceiling on what they can deliver on this data.

## 4. OMS degradation window (21:40–22:30)

| | Calls | Share |
|---|---:|---:|
| Total in the window | 2,145 | |
| Bot failure (of which `API_ERROR` 620) | 703 | **32.8 %** |
| Help | 1,095 | 51.0 % |
| Failures outside the window | 665 / 9,255 | 7.2 % |

In the 50 minutes of the window the operators would have taken 38 calls (window rate 2,574/h). The bot helped 1,095, i.e. 29.2× more. This does not remove the fault: every third caller in the window waited 8 seconds of silence and heard an apology. But the alternative is even worse: 2,107 of 2,145 would have been left without an answer.

## 5. A check that complicates the picture: transfers to the dispatcher

The bot transferred 1,026 calls to the dispatch line: 798 `connected`, 228 `queue_full`/`timeout` (`TRANSFER_FAILED`). The hour is defined by the transfer time.

| Hour | `connected` | Capacity of 3 operators | Ratio |
|---|---:|---:|---:|
| 19:00 | 101 | 45 | 2.2× |
| 20:00 | 130 | 45 | 2.9× |
| 21:00 | 162 | 45 | 3.6× |
| 22:00 | 171 | 45 | 3.8× |
| 23:00 | 138 | 45 | 3.1× |
| 00:00 | 96 | 45 | 2.1× |
| Total | 798 | 270 | 3.0× |

What this means, from the data only: in every hour there are 2–4 times more connected transfers than 3 operators can take at 4 minutes per call. So one of two things holds: the dispatch line is staffed differently from the "3 night operators" in the brief (the README states 3 dispatchers at night, a queue limit of 10), or calls to dispatchers are noticeably shorter than 4 minutes (for the peak of 171/h with three people about 1.1 min per call is needed). There is no data on the duration of the conversation with a dispatcher, so I do not establish the cause. Practical conclusion: the 45/h estimate for operators is probably **understated** for short calls, but even if tripled (135/h) the peak of 2,600/h is covered by 5.2 %. The verdict does not change.

## 6. What would change the verdict

- If Voltika were ready to put **≈ 173 operators** on at night (one operator — 15 calls/h; 2,600 / 15 ≈ 173 for the peak at 4 minutes), the bot would not be needed. That is 57.8 times more than the current 3 (section 4 of the script output, the "operators needed" row); there are no signs of such a plan in the data. *Corrected during review: the original version said "≥ 60 operators, 20 times more" — an error, 58 is the multiple relative to the team of 3 people, not the number of operators.*
- If the failure share at the peak were so high that the bot helped no more than the operators. The actual threshold: the bot's help would have to fall from 77.0 % to 2.4 % (270 calls). That is far off even in the window (51.0 %).
- If bot failures have consequences that are not in the data (repeat calls, tickets not created during a real outage, for critical subscribers). `caller_hash` makes it possible to check repeat calls, but that is outside this document.
- If the OMS degradation window recurs and `API_ERROR` stays without a fallback: then about a third of such a night will be failures. This is an argument for a fallback (ticket/SMS when `get_outage` fails), not for switching off.

## Assumptions and caveats

- 4 minutes per call, 100 % utilisation, no breaks, and no correction for the fact that operators also take transfers from the bot (that is the work of the same people, see item 5). For scenario (a) this is an upper estimate.
- No model of abandonment and repeat calls: in (a) the remaining 11,130 did not "get a refusal", some would have called again, some would have hung up. Calls are not people.
- Scenario (c) is deliberately only an upper bound: a fix does not have to produce a ticket in each of the 684 cases, especially in the window, where `create_ticket` also fails.
- "Helped" means the call outcome by label, not proven benefit to the subscriber. In the bot's answers the ETA was stale in 6.4 % of outage messages (see `docs/task2_failures_by_cause.md`), and tickets contain the bot's own phrase, not the caller's words.
- The data is fictional, one night. `OUT_OF_SCOPE` (342) is included in neither help nor failure. The hour of a transfer is defined by the time of the `transfer` event, the hour of other calls by `started_at`.
