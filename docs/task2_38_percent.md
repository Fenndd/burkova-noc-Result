# Task 2, item 1: what does "38 %" mean and is the client right?

Working document for the reviewer (Russian original, translated to English). All numbers are reproducible with a single command, see "How to reproduce". Time is everywhere **local** (Europe/Bratislava, UTC+1); in `calls.csv` it is in UTC, so 18:00Z = 19:00 local.

## Short conclusion

**Verdict: the client is half right.** The figure is correct, but the wording "just hung up on them" ("zložil") is not correct for all of the calls.

- "38 %" = `ended_by=bot` in `calls.csv`: **4,332 / 11,400 = 38.0 %**. This counts who put the phone down, not whether the caller got help. `calls.csv` and `hangup.by` in the transcripts match on 11,400 / 11,400.
- Of the 4,332 calls, **3,028 (69.9 %; 26.6 % of all calls)** are an ordinary goodbye: the bot gave the outage status, the caller replied "ďakujem", the bot said goodbye. That is a success.
- **1,304 (30.1 % of 4,332; 11.4 % of all calls)**: the bot really did cut off after an apology: `get_outage` or `create_ticket` timeout 620, address not understood 456, dispatchers busy 228. There is no fallback, and the bot hangs up by itself 4.7–9.4 s after the apology, without waiting for the caller's reply. Here the client is right.
- The dashboard **does not see** another 64 failures (the caller hung up themselves while waiting for `get_outage`). Real failures are 1,368 / 11,400 = **12.0 %**, of which the dashboard catches 95.3 %. Another 912 (8.0 %) callers left before the bot managed to help (`ENDED_EARLY`). They are not part of the "38 %".
- The share of bot-ended calls barely depends on the hour (35–42 %), while the share of real failures depends on it strongly: 7–8 % in ordinary hours, 16.7 % and 19.5 % at 21:00–22:59, 32.8 % in the OMS degradation window (21:40–22:30). The "38 %" metric does not track quality.

## How to reproduce

```
python scripts/task2_38_percent.py
```

The script takes no arguments, is deterministic, and uses only the standard library. It reads `data/calls.csv`, `data/transcripts.jsonl`, `data/oms_api_metrics.txt` and `predictions_night1.csv` (the output of `classify.py`; the script recomputes the labels via `classify.classify_call` and reports discrepancies: 0). Output sections 0–8 correspond to the tables below.

## 1. What the dashboard measures

| `ended_by` in `calls.csv` | Calls | Share of 11,400 |
|---|---:|---:|
| caller | 6,270 | 55.0 % |
| **bot** | **4,332** | **38.0 %** |
| system (transfer to dispatcher, `connected`) | 798 | 7.0 % |

Match with the transcripts: exactly one `hangup` per call, no discrepancies between `ended_by` and `hangup.by` (0 of 11,400). So the client quotes the dashboard correctly; the dispute is only about what the figure means.

## 2. What is inside `ended_by=bot` (4,332)

| Outcome (label) | Calls | % of 4,332 | % of all 11,400 | Last bot phrase |
|---|---:|---:|---:|---|
| `KNOWN_OUTAGE_INFORMED`: goodbye after the status | 3,028 | 69.9 % | 26.6 % | "Ďakujem za zavolanie, dovidenia." (1,541), "Ďakujeme, dovidenia." (1,487) |
| `API_ERROR`: `get_outage` (560) or `create_ticket` (60) timeout | 620 | 14.3 % | 5.4 % | "Ospravedlňujem sa, nastala technická chyba…" (226), "…nemôžem overiť stav siete…" (217), "…systém mi teraz neodpovedá…" (177) |
| `ADDRESS_NOT_UNDERSTOOD`: 3 attempts (396) or 2 (60) | 456 | 10.5 % | 4.0 % | "…adresu sa mi nepodarilo nájsť. Skúste prosím zavolať znova alebo poruchu nahláste cez formulár na voltika.sk." |
| `TRANSFER_FAILED`: `queue_full` (160), `timeout` (68) | 228 | 5.3 % | 2.0 % | "Všetci dispečeri sú momentálne obsadení. Skúste prosím zavolať o chvíľu znova." |
| **Total: the bot gave up** | **1,304** | **30.1 %** | **11.4 %** | |

There are no other labels among the bot-ended calls. Grouping by last phrase gives the same split as by label: a goodbye ("dovidenia") only in `KNOWN_OUTAGE_INFORMED`, and in all 1,304 failures the last phrase is an apology.

**The bot is not silent and does not cut off mid-word, but it does hang up by itself.** Before `hangup`, in 4,332 of 4,332 bot-ended calls the last event is a bot utterance. In the failed calls there is no caller utterance after the apology: the bot hangs up 4.7–9.4 s later (median 6.1 s) on its own initiative. In the goodbyes the gap is 1.7–3.2 s (median 2.6 s) and a caller utterance precedes it.

## 3. Goodbye after the status: this is a success (3,028 calls)

| Check | Result |
|---|---|
| `get_outage` returned `ok` with a non-empty `outage_id` | 3,028 / 3,028 |
| The bot spoke immediately after this result (reported the status or ETA) | 3,028 / 3,028 |
| Sequence after the status phrase | identical in all 3,028: the caller replies, the bot says goodbye, bot `hangup` |
| Caller utterances after the status | only three formulas: "dobre ďakujem" 1,082, "ďakujem" 1,051, "aha dobre" 895; no questions |
| From the status phrase to `hangup` | 8.7–12.8 s (median 10.8 s): the status was spoken and acknowledged |

**Caveat: the goodbye is routine, but the information is not always correct.** The ETA from OMS was already in the past at the moment of announcing it (comparison of `eta` with the call start plus the `t` of the bot phrase):

| Group | Stale ETA |
|---|---:|
| bot hung up (goodbye) | 182 / 3,028 = 6.0 % |
| caller hung up | 195 / 2,900 = 6.7 % |
| all `KNOWN_OUTAGE_INFORMED` | 377 / 5,928 = 6.4 % (overdue by 0–120 min, median 43 min) |

Among the 3,028 "good goodbyes", 2,846 have a correct ETA and 182 an overdue one. This does not change the label (README: "stav alebo odhad"), but 182 of 3,028 cannot be considered perfect. The client is more likely to notice this part as "the bot lied" than "the bot hung up on us".

## 4. What "38 %" does not show

| Label | ended_by=bot | ended_by=caller | ended_by=system |
|---|---:|---:|---:|
| `API_ERROR` | 620 | **64** | 0 |
| `ADDRESS_NOT_UNDERSTOOD` | 456 | 0 | 0 |
| `TRANSFER_FAILED` | 228 | 0 | 0 |
| `ENDED_EARLY` | 0 | **912** | 0 |

- **64 `API_ERROR`, ended by the caller.** They waited for `get_outage` for 4.6–7.5 s (median 6.0 s), the bot was silent the whole time, and the caller hung up. In 32 cases no result came at all, in 32 a `timeout` came after the `hangup`. For the caller this is the same failure, but the dashboard writes "caller".
- **912 `ENDED_EARLY`, ended by the caller** (8.0 % of all calls). By structure:

| What happened | Calls |
|---|---:|
| hung up at the greeting without saying anything | 365 |
| said one word ("haló", "počujete ma"…), the bot did not react, the caller hung up | 274 |
| address confirmed, `get_outage` called, the caller left before the response (an `ok` response came later; wait 0.9–6.9 s, median 2.3 s) | 273 |

The median latency of a successful `get_outage` is 1.1 s, p95 5.6 s, so the 273 calls look more like impatience than an API failure. But the bot is silent during that time. I do **not** include these 912 in "real failures": the cause cannot be determined from the logs (see caveats).

## 5. A meaningful metric: did the caller get help

| Outcome for the caller | Calls | % of 11,400 |
|---|---:|---:|
| Help received (status reported 5,928, ticket 2,052, dispatcher connected 798) | 8,778 | 77.0 % |
| Correctly sent to another line (`OUT_OF_SCOPE`) | 342 | 3.0 % |
| **Bot failure** (`API_ERROR` 684, `ADDRESS_NOT_UNDERSTOOD` 456, `TRANSFER_FAILED` 228) | **1,368** | **12.0 %** |
| Left before the bot could help (`ENDED_EARLY`) | 912 | 8.0 % |
| Total | 11,400 | 100 % |

Comparison of candidate metrics (denominator 11,400 calls):

| Metric | Value |
|---|---:|
| M1. Dashboard: the bot hung up | 4,332 = 38.0 % |
| M2. The bot hung up after giving up | 1,304 = 11.4 % |
| M3. Bot failure regardless of who hung up | 1,368 = 12.0 % |
| M4. M3 plus left early (neither help nor a failure in the pure sense) | 2,280 = 20.0 % |
| Help or legitimate redirection | 9,120 = 80.0 % |

Decomposition of the 38.0 pp: 26.6 pp routine goodbyes plus 11.4 pp failures. Recommended dashboard metric: **M3 (the share of calls where the caller did not get help because of a failure), with `ENDED_EARLY` as a separate row**; show `ended_by` as a reference only.

## 6. Dynamics by hour (local time, hour of call start)

| Hour | Calls | Bot hung up, count | Bot hung up, % | Routine goodbye, % | Real failures, count | Real failures, % | of which `API_ERROR` | of which address | of which transfer | `ENDED_EARLY`, % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 19:00–19:59 | 1,200 | 435 | 36.2 % | 28.7 % | 91 | 7.6 % | 8 | 56 | 27 | 5.4 % |
| 20:00–20:59 | 2,000 | 722 | 36.1 % | 29.1 % | 141 | 7.0 % | 11 | 92 | 38 | 6.7 % |
| 21:00–21:59 | 2,600 | 1,032 | 39.7 % | 23.9 % | 434 | 16.7 % | 273 | 104 | 57 | 10.2 % |
| 22:00–22:59 | 2,500 | 1,040 | 41.6 % | 23.5 % | 488 | 19.5 % | 368 | 76 | 44 | 9.8 % |
| 23:00–23:59 | 1,900 | 680 | 35.8 % | 29.0 % | 131 | 6.9 % | 13 | 81 | 37 | 6.7 % |
| 00:00–00:59 | 1,200 | 423 | 35.2 % | 28.5 % | 83 | 6.9 % | 11 | 47 | 25 | 6.3 % |

The OMS degradation window in `oms_api_metrics.txt` (5-minute intervals with an error rate of at least 10 %): 20:40–21:30 UTC, i.e. **21:40–22:30 local**.

| Calls | Calls | Bot hung up | Real failures | `API_ERROR` |
|---|---:|---:|---:|---:|
| start in the window 21:40–22:30 | 2,145 | 1,035 = 48.3 % | 703 = 32.8 % | 620 = 28.9 % |
| outside the window | 9,255 | 3,297 = 35.6 % | 665 = 7.2 % | 64 = 0.7 % |

Conclusions: the peak (21:00–22:59) raises the "38 %" only to 40–42 %, while it raises real failures from 7 % to 17–20 %, i.e. the dashboard barely notices the peak. The growth of failures at the peak is `API_ERROR` (the OMS window) and partly `ENDED_EARLY` (5–7 % versus 10 %). The share of address failures barely depends on the hour (3.0–4.7 % of calls), and neither does the share of failed transfers (1.8–2.3 %).

## 7. Examples for checking (`data/transcripts.jsonl`, search by `call_id`)

Goodbye, success (routine):

| call_id | Start (local) | Label | Last bot phrase |
|---|---|---|---|
| `c-n1-000004` | 19:00:05 | `KNOWN_OUTAGE_INFORMED`, bot | "Ďakujeme, dovidenia." (before that the status: "…okolo druhej hodiny v noci", ETA 02:00 is correct) |
| `c-n1-005806` | 22:00:10, peak | `KNOWN_OUTAGE_INFORMED`, bot | "Ďakujeme, dovidenia." (status: "…okolo jednej v noci", caller: "dobre ďakujem") |
| `c-n1-009227` | 23:29:34 | `KNOWN_OUTAGE_INFORMED`, bot | "Ďakujeme, dovidenia.", but the status was spoken at 23:30 and sounded "…o jedenástej večer" (ETA 23:00, overdue by 30 min) |

The bot gave up (apology and bot `hangup`):

| call_id | Start (local) | Label | Last bot phrase |
|---|---|---|---|
| `c-n1-004903` | 21:40:03, OMS window | `API_ERROR`, bot | "Je mi ľúto, systém mi teraz neodpovedá. Skúste to prosím neskôr." (`get_outage` timeout 8 s, `hangup` after 4.8 s) |
| `c-n1-000002` | 19:00:02 | `ADDRESS_NOT_UNDERSTOOD`, bot | "Ospravedlňujem sa, adresu sa mi nepodarilo nájsť. Skúste prosím zavolať znova alebo poruchu nahláste cez formulár na voltika.sk." (3 `resolve_address` in a row) |
| `c-n1-000035` | 19:01:47 | `TRANSFER_FAILED`, bot | "Všetci dispečeri sú momentálne obsadení. Skúste prosím zavolať o chvíľu znova." (the caller reported a dangerous situation; `queue_full`, `hangup` after 6.1 s) |

A failure the dashboard does not show (ended by the caller):

| call_id | Start (local) | Label | Last bot phrase |
|---|---|---|---|
| `c-n1-004208` | 21:24:06 | `API_ERROR`, caller | "Overím si: Hlavná 34, Senec. Je to správne?" The caller confirmed, `get_outage` was called at 14.6 s, the caller hung up at 21.5 s, there was no response and the bot was silent |
| `c-n1-001397` | 20:06:10 | `API_ERROR`, caller | "Overím si: Hviezdoslavova 31, Stupava. Je to správne?" `hangup` at 25.2 s, `timeout` came at 25.7 s (after the hangup) |
| `c-n1-000078` | 19:03:47 | `ENDED_EARLY`, caller | "Overím si: Školská 37, Pezinok. Je to správne?" `hangup` at 19.6 s, `ok` came at 20.1 s (left 0.5 s before the response) |

Checked by hand against the raw lines of `transcripts.jsonl` and `calls.csv`: `c-n1-005806`, `c-n1-004903`, `c-n1-004208` and `c-n1-009227` (ETA, last phrases, moment of `hangup`, start time all matched).

## 8. Caveats: what the data do not say

- **The unit of counting is the call, not the person.** There are 10,300 unique `caller_hash`es, 815 of them called more than once. "12 % of calls with a failure" does not equal "12 % of people without help": some people got help by calling again.
- **I have not seen the dashboard.** The definition "`ended_by=bot`" is inferred from the fact that it gives exactly 38.0 % and matches the transcripts.
- **The labels are obtained automatically** (`classify.py`, 60 of 60 on the labeled sample). The sample is small; the split is confirmed by the event structure, but not by a manual check of all 11,400.
- **"Help received" is understood formally.** In 2,112 of 2,112 `create_ticket` calls, the bot's own last phrase went into `description`, not the caller's description (checked by script). A ticket was created, but whether it is usable for a technician, the data do not say. This is a separate question and is not part of the "38 %" calculation.
- **The stale ETA** is computed from the `eta` field and the time of announcement; what exactly the bot said is taken from the utterance text, not from audio. Whether the caller noticed the problem is unknown.
- **The callers' reaction to the apology is unknown.** There is no data on repeat calls at the same moment, on complaints, or on what the caller really heard (no audio, only transcripts).
- **`ENDED_EARLY` (912) is ambiguous.** 365 people hung up at the greeting after 1.5–5.0 s (median 3.4 s); 274 said "haló" and hung up after 1.1–4.8 s (median 2.9 s) without any reaction from the bot; 273 left after 0.9–6.9 s of waiting for a response. Part of them is the bot's fault (no repeated question, no "I am checking"), part is impatience. Therefore metric M3 (12.0 %) is a lower estimate and M4 (20.0 %) an upper one.
- **Hour = hour of call start.** A call started at 21:39 but waiting for a response after 21:40 falls into "outside the window"; the shift is small. The window is taken from the rows of `oms_api_metrics.txt` with an error rate of at least 10 %.
- One night, one flow version (`v14`): there is nothing to compare with.
