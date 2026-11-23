# Tasks 2–4 — Voltika, storm night Sun 15. 11. 2026

All numbers are reproducible: `python scripts/task2_38_percent.py`, `python scripts/task2_failures.py`, `python scripts/task4_capacity.py` (labels come from `classify.py` → `predictions_night1.csv`). Times are local (UTC+1). Detailed evidence and the full fix backlog are in `docs/` (branch `full`, see `README.md`).

## 2. Numbers

**What "38 %" means — the client is partly right.** It is `ended_by=bot` (4,332 / 11,400): *who ended* the call, not whether the caller was helped.
- 3,028 of them (69.9 %) were a normal goodbye after the bot announced the outage and ETA.
- 1,304 (11.4 % of all calls) were real give-ups: the bot apologised and hung up, no fallback. Here she is right.
- Overall **8,778 / 11,400 (77.0 %) were helped** (status, ticket or dispatcher).

**Real failures: 1,368 / 11,400 (12.0 %), by cause and owner of the fix**

| Cause | Calls | Who fixes it |
|---|---:|---|
| `get_outage` (Voltika OMS) gave no answer; 561 of 624 in the OMS degradation window 21:40–22:30 | 624 | Voltika: OMS capacity. Us: fallback instead of hanging up |
| Address not understood: 247 low ASR confidence, 209 resolver (town parts, wrong town) | 456 | Product team: resolver, ASR |
| Transfer to dispatch failed (160 `queue_full`, 68 `timeout`), no ticket created | 228 | Us: danger ticket first, then transfer and wait. Voltika: queue limit 10, danger priority |
| `create_ticket` timeout, 54 of 60 in the same window | 60 | Product team |

- Borderline: 912 calls (8.0 %) ended early; counting them all gives an upper bound of 20.0 %.
- Quality issue: 377 callers got an ETA that had already passed (Voltika fixes the data; we stop reading out past times).

## 3. Reply to the client (Slovak, ready to send)

**Predmet:** Re: Včerajšia noc

Dobrý deň, pani Hudecová,

ospravedlňujem sa všetkým, ktorým bot nepomohol.

Medzi 19:00 a 01:00 prišlo 11 400 hovorov, v špičke 2 600 za hodinu (traja noční operátori zvládnu asi 45). Údaj 38 % ukazuje, kto hovor ukončil, nie ako dopadol: 3 028 zo 4 332 hovorov, ktoré ukončil bot, bolo bežné rozlúčenie po oznámení poruchy a času obnovy.

Pomoc dostalo 8 778 volajúcich (77 %). Nedostalo ju 1 368 (12 %):
- 684 – systém porúch alebo zakladanie hlásení neodpovedali včas, najmä 21:40–22:30; bot nemal náhradný postup a hovor ukončil,
- 456 – bot nerozpoznal adresu,
- 228 – nebezpečné situácie pri preťaženom dispečingu.

Upravujeme bota, aby v týchto prípadoch nezložil, ale založil hlásenie a pri nebezpečenstve počkal na dispečera, a zlepšujeme rozpoznávanie adries. Spomalenie systému porúch riešime s vaším IT. Termíny pošlem do piatku.

SMS s odhadom obnovy pripravíme. Pomôžu nám vaše odpovede:
1. Má SMS dostať len ten, kto volal, alebo aj odberatelia na postihnutej adrese? Máte ich čísla a súhlas?
2. Poslať novú SMS, keď sa odhad zmení, a po obnovení dodávky?
3. Čo poslať, ak odhad ešte nie je známy?
Termín potvrdím po vašich odpovediach a po overení, že odhady sú aktuálne.

S pozdravom

## 4. Next steps

- **Order — safety first, then the biggest failure groups, then what we can ship ourselves.**
  1. Before the next storm, our team changes the flow:
     - danger cases: create a ticket, then transfer, and keep waiting if the queue is full (228 calls);
     - fallback when `get_outage` / `create_ticket` fail (684 calls, 50 % of failures);
     - re-prompt when the caller says only "haló" (274 calls).
  2. Start with Voltika right away: they have the longest lead time and root cause no. 1. They need to load-test and scale OMS for a ≈ 2,600 calls/h peak and add danger priority in the dispatch queue.
  3. In parallel, the product team fixes the resolver town parts and ASR.
  4. The dashboard should measure call outcome ("helped / failed by cause") instead of `ended_by`.
- **SMS "from next week": yes, but not blindly from Monday.**
  - 377 callers were already given an ETA that had passed; an SMS would put that error in writing.
  - We give a date after the client answers the questions in the email (task 3) and after we add a stale-ETA check.
  - Phase 1: SMS only to people who called, only with a current ETA.
  - Phase 2: proactive SMS and updates, once Voltika decides on phone numbers and consent (GDPR) and OMS is fixed.
- **Switch the bot off? No — fix it.**
  - Capacity: 3 night operators × 60/4 min = 45 calls/h, against a peak of 2,600/h (57.8×).
  - Without the bot at most 270 of 11,400 calls (2.4 %) would have been answered; with the bot 8,778 (77.0 %) were helped.
  - Even in the worst OMS window the bot helped 1,095 callers; operators could have taken 38 in those 50 minutes.
  - Replacing the bot would need ≈ 173 night operators.

Details — priorities P0–P2 per team, ordering rationale, SMS phases, capacity table: `docs/fix_backlog.md`, `docs/task2_*.md`, `docs/task4_switch_off.md`.
