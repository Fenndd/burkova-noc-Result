# Task 2, item 2: how many calls really failed and why

Question from the README: "Koľko hovorov reálne zlyhalo a prečo? Rozdeľ to podľa príčin."
Causes only. I do not assign fix owners or priorities here (those are other items). Working document in English (translated from the Russian original), for review.

All numbers below are taken from the output of `python scripts/task2_failures.py` (night 1, 11,400 calls, labels from `classify.py`; the match with `predictions_night1.csv` is checked by the script: 0 discrepancies). Times are local (UTC+1).

## Summary

- **Real failure** = the caller left without the help the line exists for, through the fault of the bot or the system: labels `API_ERROR` + `ADDRESS_NOT_UNDERSTOOD` + `TRANSFER_FAILED`.
- **Total: 1,368 of 11,400 = 12.0 %.** For comparison: the client's "38 %" is `ended_by = bot` (4,332); real failures among them are 1,304 (30.1 %), the remaining 3,028 are not failures by this definition.
- The borderline group `ENDED_EARLY` (912, not included): if we add the sub-case "hung up while the response was already on its way" (273), we get **1,641 = 14.4 %**; plus "haló" with no bot reaction (274), **1,915 = 16.8 %**; the upper bound with any early departure (912) is **2,280 = 20.0 %**.
- Causes by size (share of 1,368):
  1. `get_outage` failure/unavailability: **624** (45.6 %; 5.5 % of all calls). 561 of 624 (89.9 %) fall into the OMS degradation window 21:40–22:30.
  2. Address not determined: **456** (33.3 %): 247 low ASR confidence throughout; 149 well recognised but not found; 60 the resolver returned someone else's address. 55.9 % of these calls mention one of 4 town parts (Grinava, Cajla, Kráľová, Harmónia).
  3. Transfer to dispatch failed: **228** (16.7 %): 160 `queue_full`, 68 `timeout`.
  4. `create_ticket` timeout: **60** (4.4 %); 54 of 60 in the same window 21:40–22:30.
- Quality inside the "successful" calls (not failures): a stale ETA in 377 of 5,928 outage announcements (6.4 %); in 2,112 of 2,112 tickets the description = the bot's own phrase, not the caller's words; the `get_outage` responses are inconsistent.

## How to reproduce

```
python scripts/task2_failures.py            # ~2 s, stdlib only, deterministic (verified: two runs give byte-identical output)
python scripts/check_outage_consistency.py  # only for item 5c
```

The script imports `classify.py`, prints every number of this document and example calls (with local time and events). The cause of `API_ERROR` and the sub-cases of `ENDED_EARLY` are determined by event structure (which tool, `status` ok / not ok, who hung up, timings); bot text is not matched. `asr_conf` is used only as a descriptive correlate.

The degradation window definition is derived automatically from `data/oms_api_metrics.txt`: fully degraded buckets (error_rate ≥ 20 %, p95 = 8,000 ms) 20:40Z–21:25Z = **21:40–22:30 local**; the tail bucket 21:30Z (22:30–22:35 local: p95 7,081 ms, 4.2 %) is counted separately.

---

## 1. API_ERROR (684 = 6.0 % of calls)

Calls that invoked `get_outage`: 9,451; `create_ticket`: 2,112.

| Cause | Calls | Denominator | Share |
|---|---:|---|---:|
| `get_outage` timeout, the caller waited, the bot apologised and hung up | 560 | 9,451 `get_outage` calls | 5.9 % |
| the caller hung up while waiting for `get_outage`; result later: timeout | 32 | 9,451 | 0.3 % |
| the caller hung up while waiting for `get_outage`; no result in the log | 32 | 9,451 | 0.3 % |
| **`get_outage` total** | **624** | 9,451 | **6.6 %** |
| `create_ticket` timeout (outage unknown, no ticket) | 60 | 2,112 `create_ticket` calls | 2.8 % |

All 652 failed calls have `latency_ms = 8000` (the cap). The caller waited 8 seconds in silence. After the result the bot apologised with one of three phrases and hung up 4.7–6.4 s later (median 5.5 s). There are no words like "visit the website" or "we will leave a ticket" in these phrases. 64 callers (32 + 32) hung up themselves after 4.6–7.5 s of waiting (median 6.0 s). These 64 are the only real failures where it was not the bot that hung up.

### Time: correlation with the OMS degradation window

| Phase (local time) | `get_outage` calls in the records | no response | % | requests in OMS metrics | OMS errors (estimate) | median `latency_ms` of ok responses |
|---|---:|---:|---:|---:|---:|---:|
| before the window (19:00–21:40) | 4,034 | 32 | 0.8 % | 4,033 | 32 (0.8 %) | 1.00 s |
| **window (21:40–22:30)** | **1,764** | **561** | **31.8 %** | 1,762 | 559 (31.7 %) | **4.95 s** |
| tail (22:30–22:35) | 163 | 5 | 3.1 % | 166 | 7 (4.2 %) | 1.04 s |
| after (22:35–01:00) | 3,490 | 26 | 0.7 % | 3,490 | 26 (0.7 %) | 1.00 s |

- The number of calls in the records matches "requests" in Voltika's metrics (9,451 in total both there and here): the records and the metrics describe the same traffic.
- Over the 73 five-minute buckets, the Pearson correlation between the OMS `error_rate` and the share of calls without a response in the records is **r = 0.999**.
- Buckets around the window (in the records: calls / without response; in the metrics: p95 / error): 21:35 — 179 / 1 (0.6 %) · p95 2,238 ms; **21:40 — 203 / 61 (30.0 %) · p95 8,000 ms, 29.6 %**; … **22:25 — 185 / 65 (35.1 %) · 8,000 ms, 35.8 %**; 22:30 — 163 / 5 (3.1 %) · 7,081 ms, 4.2 %; 22:35 — 173 / 0.
- Inside the window there are 561 of 624 (89.9 %) `get_outage` failures; outside the window the background is single digits (0.7–0.8 %).

Cause by phase (by the time of the tool call itself):

| Phase | timeout, bot apologised | caller left, later timeout | caller left, no result | `create_ticket` timeout |
|---|---:|---:|---:|---:|
| before the window | 29 | 2 | 1 | 2 |
| window | 507 | 28 | 26 | 54 |
| tail | 4 | 0 | 1 | 0 |
| after | 20 | 2 | 4 | 4 |

### `create_ticket`: also fails in the window

| Phase | `create_ticket` calls | failed | % |
|---|---:|---:|---:|
| before the window | 935 | 2 | 0.2 % |
| **window** | **299** | **54** | **18.1 %** |
| tail | 38 | 0 | 0.0 % |
| after | 840 | 4 | 0.5 % |

Per the README, `create_ticket` is our tool, not a Voltika API, but its failures are concentrated in the same window as the OMS failures. The data do not show why (a shared dependency, a cascade, shared load); this is an open question, not a conclusion.

### Evidence (open in `data/transcripts.jsonl`)

- **c-n1-004903**, start 21:40:03 (inside the window). `get_outage` called at 21:40:19 (t = 16.5 s); result `timeout`, `latency_ms: 8000`, after 8.0 s (t = 24.5); bot: "Je mi ľúto, systém mi teraz neodpovedá. Skúste to prosím neskôr."; `hangup by bot` at t = 29.3.
- **c-n1-000105**, start 19:05:05 (background, before the window). The same scenario; bot: "Prepáčte, momentálne nemôžem overiť stav siete. Zavolajte nám prosím o chvíľu znova."
- **c-n1-001397**, start 20:06:10. `get_outage` at t = 17.7; `hangup by caller` at t = 25.2 (waited 7.5 s); `tool_result timeout` came at t = 25.7, 0.5 s after the departure.
- **c-n1-004208**, start 21:24:06. `get_outage` at t = 14.6; `hangup by caller` at t = 21.5; no result in the log.
- **c-n1-004936**, start 21:40:42 (window). `get_outage ok` with `outage_id: null` (4.9 s), caller: "susedia elektrinu majú my nie"; `create_ticket` at t = 30.6 → `timeout` 8,000 ms at t = 38.6; bot: "Ospravedlňujem sa, nastala technická chyba. Skúste prosím zavolať neskôr."
- **c-n1-004390**, start 21:28:11 (before the window, one of the 6 `create_ticket` timeouts outside the window). The same outcome; bot: "Je mi ľúto, systém mi teraz neodpovedá. Skúste to prosím neskôr."

---

## 2. ADDRESS_NOT_UNDERSTOOD (456 = 4.0 % of calls)

Denominator: calls that reached `resolve_address`, **9,907**; of them 456 failed (**4.6 %**). In all 456 the bot hung up itself: 396 after three failed attempts, 60 after two addresses rejected by the caller.

| Group (mutually exclusive) | Calls | Share of 456 | Condition |
|---|---:|---:|---|
| A. low ASR confidence throughout | 247 | 54.2 % | all attempts with `asr_conf < 0.8`, address not found |
| B. well recognised, still not found | 149 | 32.7 % | at least one attempt with `asr_conf ≥ 0.8`, address not found |
| C. the resolver returned an address, the caller rejected it | 60 | 13.2 % | `resolve_address ok`, caller: "nie…", twice in a row |

### Link to `asr_conf` (correlation, not cause)

Share of failed attempts (`status ≠ ok`) by recognition confidence of the utterance, 11,642 attempts in total:

| `asr_conf` | attempts | failures |
|---|---:|---:|
| < 0.5 | 414 | 100 % |
| 0.5–0.6 | 663 | 100 % |
| 0.6–0.7 | 542 | 100 % |
| 0.7–0.8 | 330 | 85.2 % (281) |
| 0.8–0.9 | 4,649 | 3.7 % (171) |
| ≥ 0.9 | 5,044 | 0 % |

The boundary is almost a step function (≈ 0.75): below it the resolver finds nothing. In 266 of 2,071 failed attempts (12.8 %) the text contains no name of a locality at all (the text is garbled). From this it cannot be inferred whether the ASR erred or the resolver discards uncertain input (see limitations).

### Town parts

A call is attributed to a town part if the name of the part appears in the text of any attempt (Grinava, Cajla are parts of Pezinok; Kráľová, Harmónia are parts of Modra).

| Locality | calls (with an attempt) | address failure | failed attempts | failures among attempts with `asr ≥ 0.8` |
|---|---:|---:|---:|---:|
| Grinava | 188 | 69 (36.7 %) | 186/319 (58.3 %) | 28/154 (18.2 %) |
| Cajla | 187 | 65 (34.8 %) | 162/306 (52.9 %) | 27/164 (16.5 %) |
| Kráľová | 184 | 59 (32.1 %) | 153/294 (52.0 %) | 22/156 (14.1 %) |
| Harmónia | 178 | 62 (34.8 %) | 156/292 (53.4 %) | 22/151 (14.6 %) |
| **4 parts together** | **737** | **255 (34.6 %)** | **657/1,211 (54.3 %)** | **99/625 (15.8 %)** |
| 10 ordinary towns together | 9,170 | 201 (2.2 %) | 1,414/10,431 (13.6 %) | 72/9,068 (0.8 %) |
| average over all attempts | — | — | 2,071/11,642 (17.8 %) | — |

Range across the 10 ordinary towns: address failure 1.5–3.2 %. Town parts are 7.4 % of the calls that reached the resolver, but 255 of 456 (**55.9 %**) of the address failures. Among failures at `asr ≥ 0.8`, 99 of 171 (57.9 %) fall on calls with a town part. By group: A 134/247 (54.3 %), B 85/149 (57.0 %), C 36/60 (60.0 %).

### Group C (the resolver returned someone else's address)

- In 60 of 60 calls, the same `address_id` came back on both attempts, and the town in the confirmation ("Overím si: …, <town>") does not match the town the caller named (60 of 60). The callers replied "nie nie ja som z inej obce" (25), "nie to nie je moja adresa" (18), "nie to je zle" (17).
- The `asr_conf` of the utterances in C: from 0.7 to 0.9, median 0.8, i.e. the speech was recognised well.
- Control: in all other calls of the night where the address was accepted, the town in the confirmation matches the named one (0 discrepancies outside these 60). There are no silently accepted wrong addresses in the data.

### Evidence

- **A: c-n1-000037**, start 19:01:53. Utterances: "no senec slovenského národného povstania 58" (asr 0.49) → `no_match`; "takže es en pé 58 senec" (0.79) → `ambiguous`; "no slovenského národného povstania 58 senec" (0.76) → `no_match`. Bot: "Ospravedlňujem sa, adresu sa mi nepodarilo nájsť. Skúste prosím zavolať znova alebo poruchu nahláste cez formulár na voltika.sk."; `hangup by bot` t = 39.9.
- **B (town part): c-n1-000002**, start 19:00:02. "krátka trinásť pezinok grinava" (asr 0.83) → `no_match`; then 0.60 and 0.46, both `no_match`.
- **B (ordinary town): c-n1-000127**, start 19:06:17. "svätý jur prvého mája päťdesiat lomeno a" (asr 0.80) → `ambiguous` (house "50/A"); then 0.55 and 0.60, `ambiguous` again.
- **C: c-n1-000086**, start 19:04:05. "námestie slobody 7 modra kráľová" (asr 0.90) → `ok` A-002611, bot: "Overím si: Nám. slobody 3, Limbach. Je to správne?"; caller: "nie nie ja som z inej obce"; the same A-002611 again; "nie to je zle"; the bot gives up.

---

## 3. TRANSFER_FAILED (228 = 2.0 % of calls)

There were 1,026 transfer attempts in total (9.0 % of calls), 228 failed (**22.2 %**). All 1,026 calls received the phrase "Toto je nebezpečná situácia. Prepájam vás na dispečing, nezatvárajte.".

| Outcome | Calls | Denominator | Time from "Prepájam" to the result |
|---|---:|---|---|
| `connected` (success, for comparison) | 798 | 1,026 | 8.9–44.9 s, median 27.1 s |
| `queue_full` | 160 | 1,026 (15.6 %) | 5.9–8.0 s, median 7.0 s |
| `timeout` | 68 | 1,026 (6.6 %) | 64.8–65.1 s (≈ 65 s of waiting) |

With and without an address (address = there was at least one `resolve_address`):

| | transfers | failures | `queue_full` | `timeout` |
|---|---:|---:|---:|---:|
| the bot managed to ask for the address | 514 | 114 (22.2 %) | 80 | 34 |
| transfer before the address question | 512 | 114 (22.3 %) | 80 | 34 |

There is no difference in the failure share; in the 114 failed calls without an address, neither the dispatcher nor the system received an address or a description.

What the caller heard. After a failure, in all 228 cases the same phrase (for `queue_full` and for `timeout`): "Všetci dispečeri sú momentálne obsadení. Skúste prosím zavolať o chvíľu znova.", then `hangup by bot` after 5.8–6.1 s. No ticket was created in any of the 228 (0), and there is no other number or alternative in the text. In the `timeout` case the caller, who was asked not to hang up ("nezatvárajte"), had to wait about 65 s to hear the same thing.

By local hour (call start): the share of failed transfers is 20.5–26.1 %, with a maximum of 26.1 % at 21:00–22:00 (57 of 218). A flat curve: this is not a load peak on our line.

Check of the queue limit of 10: at the moment of the `queue_full` result, between 0 and 6 other bot transfers were waiting simultaneously (median 1); it never reached 10. So `queue_full` is not explained by the bot's own transfers; Voltika's queue is busy with something else (with what exactly, the data do not show).

Repeat calls: 68 of 228 failures (29.8 %) were followed later by a successful call from the same `caller_hash`.

### Evidence

- **c-n1-000035**, start 19:01:47. Caller (asr 0.96): "padol strom na vedenie"; bot: "Toto je nebezpečná situácia. Prepájam vás na dispečing, nezatvárajte." (t = 9.4); `transfer dispatch queue_full` at t = 15.4; bot: "Všetci dispečeri sú momentálne obsadení…"; `hangup by bot` t = 21.5. No address, no ticket.
- **c-n1-000108**, start 19:05:13. Address found, `get_outage ok` with `outage_id: null`, caller: "iskrí to zo stĺpa"; "Prepájam…" at t = 26.2; `transfer timeout` at t = 91.3 (65 s); then the same phrase about busy dispatchers and `hangup by bot` t = 97.3. No ticket.
- **c-n1-000177**, start 19:09:15. Address Záhradná 60, Šamorín found, `outage_id: null`; caller: "spadnutý drôt na ceste pred domom"; `transfer queue_full` at t = 32.5; no ticket created.

---

## 4. ENDED_EARLY (912 = 8.0 %): a borderline group, not included in failures

The label per the README: the call ended earlier, "a nespôsobilo to zlyhanie nástroja ani prepojenia". But there are different situations inside it. Baseline values for comparison: in ordinary calls the caller starts speaking no earlier than 6.9 s (median 7.8 s); from the caller's first utterance to the bot's next action 1.3–6.4 s pass (median 2.5 s, p90 3.6 s).

| Sub-case | Calls | What is in the record | Bot's fault |
|---|---:|---|---|
| E1. hung up at the greeting | 365 | only `bot` (greeting) and `hangup caller` at 1.5–5.0 s (median 3.4 s) | not attributed: all 365 left before any normal caller even started to speak (6.9 s) |
| E2. "haló", the bot did not react | 274 | one caller utterance ("haló haló" 66, "ehm" 58, "počujete ma" 56, "haló" 55, "no" 39) and `hangup`, not a single bot event | possibly, not proven |
| E3. hung up while `get_outage` was still running; ok came later | 273 | `get_outage` called, `hangup caller`, then `result ok` | **probably yes** (see below) |
| other | 0 | | |

**E2.** From the utterance to `hangup`: 1.1–4.8 s (median 2.9 s). 173 of 274 (63.1 %) waited longer than the usual median bot reaction (2.5 s), 69 (25.2 %) longer than its p90 (3.6 s). That is, in about a quarter of cases the bot was slower than 90 % of normal reactions; the rest left within the usual reaction time. But in 274 of 274 such cases the bot did nothing at all: it did not call `resolve_address`, did not ask again. All calls where the first utterance equals one of these five phrases ended exactly this way (274 of 274). For comparison: of the other calls, 844 with a first utterance of `asr_conf < 0.7`, in 844 the bot tried the resolver, i.e. low `asr_conf` by itself does not switch off the reaction. The share of E1+E2 is higher at 21:00–22:00 (7.2 % and 7.0 % of the hour's calls) than in other hours (3.5–4.7 %). The data do not show the cause.

**E3.** The caller waited in silence for 0.9–6.9 s (median 2.3 s); between the `get_outage` call and the departure there is not a single bot event (273 of 273). The request actually took 1.6–7.3 s (median 2.8 s versus 1.0 s normally), and the ok response came 0.3–0.7 s after the departure. This is the only sub-case where the caller already had an answer almost immediately after leaving, which they did not hear. The cause is twofold: a slow OMS (the share of E3 among `get_outage` calls is 4.8 % in the window versus 2.4 % outside it) and silent waiting in the bot itself. 181 of 273 cases (66 %) happened outside the window and tail (before the window 98, after 83), i.e. under ordinary OMS operation with isolated slow requests.

Share of those who left before the response among ok responses, by request duration: < 1 s — 0/3,809; 1–2 s — 40/3,506 (1.1 %); 2–3 s — 129/334 (38.6 %); 3–5 s — 56/584 (9.6 %); ≥ 5 s — 48/594 (8.1 %). The curve is non-monotonic, so no "patience threshold" can be derived from it.

### Final numbers including the borderline group

| What we count | Calls | Share of 11,400 |
|---|---:|---:|
| real failures (API_ERROR + ADDRESS + TRANSFER_FAILED) | **1,368** | **12.0 %** |
| + E3 (left while an ok response was already on its way) | 1,641 | 14.4 % |
| + E3 + E2 ("haló", the bot is silent) | 1,915 | 16.8 % |
| + all ENDED_EARLY (including E1), upper bound "without help" | 2,280 | 20.0 % |

### Evidence

- **E1: c-n1-000029**, start 19:01:31: greeting, `hangup by caller` at t = 2.7.
- **E2: c-n1-000082**, start 19:04:00: "počujete ma" (asr 0.68) at t = 7.2; `hangup by caller` at t = 11.9; no bot events after the greeting.
- **E3: c-n1-000078**, start 19:03:47: `get_outage` at t = 17.1; `hangup by caller` at t = 19.6; `result ok` (latency 2,997 ms, O-5147, ETA 02:00) at t = 20.1. **c-n1-004909**, start 21:40:10 (in the window): `get_outage` at t = 16.9; departure at t = 20.9; `result ok` (4,640 ms) at t = 21.5.

---

## 5. Quality problems inside "successful" calls (not failures)

The label of these calls is correct (`KNOWN_OUTAGE_INFORMED`, `TICKET_CREATED`), but the caller's experience is poor.

**5a. The ETA is already in the past at the moment the bot announced it.** 377 of 5,928 `KNOWN_OUTAGE_INFORMED` (6.4 %); of them more than 15 min in the past 312 (5.3 %), more than 60 min 109 (1.8 %); median 43 min, maximum 120 min. The caller hung up in 195, the bot in 182. Evidence **c-n1-009261** (start 23:30:16): result at 23:30:33, `eta: 2026-11-15T23:00:00+01:00`, bot: "Na vašej adrese evidujeme poruchu. Elektrinu by ste mali mať späť o jedenástej večer." That is, a promise for 30 minutes ago.

**5b. The ticket description is not the caller's words.** In 2,112 of 2,112 `create_ticket` calls (100 %) the `description` field equals the bot's previous phrase "Na vašej adrese zatiaľ poruchu neevidujeme. Opíšte mi prosím, čo sa stalo.", although in 2,112 of 2,112 calls the caller said something after that. **c-n1-000005** (19:00:05): the caller "vyhodilo ističe a nejde to nahodiť" (asr 0.97), the bot's phrase went into `create_ticket`. **c-n1-004936**: "susedia elektrinu majú my nie".

**5c. Inconsistent `get_outage` responses.** Details: [outage_consistency_evidence.md](outage_consistency_evidence.md); I did not recompute them, I ran `scripts/check_outage_consistency.py` and checked the headline numbers: for one `address_id`, consecutive responses ≤ 5 min apart differ in 744 of 817 pairs (91.1 %), the "outage exists / not" flip in 347 of 817 (42.5 %), both "yes" with a different `outage_id` 397 of 397. An important caveat from the same document: the statistics are indistinguishable from random, possibly it is an artefact of a fictional dataset.

## 6. People, not calls

Among the 1,368 failed calls there are 1,304 unique `caller_hash`es. Of them 319 (24.5 %) got help (`KNOWN_OUTAGE_INFORMED`, `TICKET_CREATED` or `TRANSFERRED`) later the same night; 985 did not in the data. In total 345 of the 1,368 failed calls (25.2 %) have a successful call from the same number later. By type: `API_ERROR` 151/684, `ADDRESS_NOT_UNDERSTOOD` 126/456, `TRANSFER_FAILED` 68/228.

## 7. Failures by hour (call start)

| Hour | calls | API_ERROR | ADDRESS | TRANSFER_FAILED | real, % | ENDED_EARLY |
|---|---:|---:|---:|---:|---:|---:|
| 19:00 | 1,200 | 8 | 56 | 27 | 7.6 % | 65 |
| 20:00 | 2,000 | 11 | 92 | 38 | 7.0 % | 133 |
| 21:00 | 2,600 | 273 | 104 | 57 | 16.7 % | 265 |
| 22:00 | 2,500 | 368 | 76 | 44 | 19.5 % | 245 |
| 23:00 | 1,900 | 13 | 81 | 37 | 6.9 % | 128 |
| 00:00 | 1,200 | 11 | 47 | 25 | 6.9 % | 76 |

The surge at 21:00–23:00 is entirely `API_ERROR`; address failures (3.0–4.7 % of the hour's calls) and transfers (20.5–26.1 % of attempts) barely depend on the hour.

## 8. Summary table: cause, calls, % of all, % of failures

| Cause | Calls | % of 11,400 | % of 1,368 |
|---|---:|---:|---:|
| `get_outage` timeout, the caller waited, the bot apologised | 560 | 4.91 % | 40.9 % |
| address: `asr < 0.8` throughout | 247 | 2.17 % | 18.1 % |
| transfer: `queue_full` | 160 | 1.40 % | 11.7 % |
| address: well recognised (≥ 0.8), but not found | 149 | 1.31 % | 10.9 % |
| transfer: `timeout` | 68 | 0.60 % | 5.0 % |
| `create_ticket` timeout | 60 | 0.53 % | 4.4 % |
| address: the resolver returned an address, the caller rejected it | 60 | 0.53 % | 4.4 % |
| `get_outage`: caller left, later timeout | 32 | 0.28 % | 2.3 % |
| `get_outage`: caller left, no result | 32 | 0.28 % | 2.3 % |
| **Total real failures** | **1,368** | **12.00 %** | **100 %** |

By stage: `get_outage` 624 (5.47 %; 45.6 %), address 456 (4.00 %; 33.3 %), transfer 228 (2.00 %; 16.7 %), `create_ticket` 60 (0.53 %; 4.4 %). The rows do not overlap, there is no remainder. The "town part" feature (255 calls) and the "in the degradation window" feature (561 + 54 calls) are slices on top of these rows, not separate causes.

## Limitations (what the data do not say)

- **The data are fictional.** The patterns look generated: the resolver status depends almost as a step function on `asr_conf`, the share of failed transfers is flat by hour, the OMS responses are random. Conclusions about the real cause cannot be transferred to a real system without logs.
- **`asr_conf` is a correlation.** From a single utterance one cannot tell "the ASR erred" from "the resolver discarded uncertain input". The text of failed attempts often looks correct (in 87.2 % of failures the text contains a town name). Whether the address is correct, the data do not show: there is no address registry. The division A / B / C is conventional (threshold 0.8).
- **Town parts.** The list of four names is taken from what the bot itself pronounces in the confirmation; ASR distortions of the names in the text may not be counted, so the share is understated, not overstated.
- **What the caller would do.** E1–E3 are caller behaviour; the "bot's fault" in E2 and E3 is based on the absence of reaction and on silence, not on knowing the reason for leaving. The E2 thresholds (median and p90 of the bot's reaction) are taken from the same night.
- **The cause of the `create_ticket` failures in the window is unknown** (it is ours per the README). The data show a coincidence in time, not a mechanism.
- **The dispatch queue.** Its length and composition are not shown by the data, only the outcome (`queue_full`, `timeout`, `connected`) and the fact that ≥ 10 simultaneous bot transfers were never reached.
- **Calls are not people.** `caller_hash` is a hash of the number, one number may be several people; "got help later" means "there was a successful call from this number", not necessarily about the same issue.
- **Time accuracy.** Event time = `started_at` (UTC) + `t` + 1 hour; 15. 11. 2026 is already after the switch to winter time. The degradation window in client time is 21:40–22:30 (with a tail up to 22:35).
- **`API_ERROR` with `ended_by = bot`.** Per `calls.csv`, for 620 of the 684 `API_ERROR` the bot hung up, for 64 the caller (the same 32 + 32 from the table in section 1). Between the `get_outage` call and the result, in 560 of 560 calls with an apology the bot was silent.
