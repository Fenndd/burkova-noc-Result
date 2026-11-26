# Night 2: network drop after the first failed address attempt — 75 calls

All numbers: `python scripts/night2_network_drops.py` (night 2, 4,000 calls, flow v15; for comparison it also reads night 1 from `data/`).
The calls in readable form: [calls_network_drop_night2.md](calls_network_drop_night2.md). That file is not committed because it contains the assignment's call data. The same command generates it.

## Summary

Night 2 brought a new value `hangup.by = network`: the network cut the call. There are 150 such calls, split into two equal groups of 75.

| Group | What happened | Label before N1 | Better-fitting label |
|---|---|---|---|
| **A** | The resolver did not find the address on the first attempt (`no_match`). The bot asked the caller to repeat it, and the connection dropped while the caller was answering | `ADDRESS_NOT_UNDERSTOOD` | **`ENDED_EARLY`** |
| B | The resolver found the address, the caller confirmed it ("áno", "správne"), and the connection dropped right after | `ENDED_EARLY` | `ENDED_EARLY`, not contested |

Only group A was contested. There was no bug in the code: the classifier did exactly what the specification said (§4.3, decision B1). The question was whether that rule fits the new scenario "the connection dropped".

## The group A scenario

All 75 calls look the same. Example `c-n2-000045`:

```text
   0.0  BOT      Dobrý večer, tu je Voltika, linka pre poruchy. Na akej adrese vám nejde prúd?
   6.9  CALLER   sv ätý jur mlynská 16   (asr 0.45)
   9.0  CALL     resolve_address {"text": "sv ätý jur mlynská 16"}
   9.3  RESULT   resolve_address no_match 253ms —
   9.3  BOT      Tú adresu nemôžem nájsť. Skúste mi ju povedať ešte raz, aj s názvom obce.
  15.0  HANGUP   by network
```

What all 75 have in common:
- exactly one `resolve_address` attempt, with status `no_match` in all 75;
- `get_outage` was never called;
- the last event before the drop is the bot line "Tú adresu nemôžem nájsť. Skúste mi ju povedať ešte raz, aj s názvom obce.", identical in all 75 calls;
- the drop comes 5.7–8.2 s after that line (median 6.9 s), most likely while the caller was repeating the address;
- the mean `asr_conf` of the first utterance is 0.53, so recognition was poor. The addresses contain split words: "sv ätý jur", "záhr adná", "hviezdo slavova".

For comparison, a twin call from group B, `c-n2-000012`:

```text
  11.4  BOT      Rozumiem, Hviezdoslavova 22, Pezinok. Sedí to?
  16.7  CALLER   hej   (asr 0.85)
  17.1  HANGUP   by network
```

## What the classifier returned before N1, and why

The call went through the specification steps like this:
1. No `transfer`.
2. No outcome episode: no ticket, no reported status, no `route`.
3. §4.3, the last uncorrected failure: there was a `resolve_address`, `get_outage` was not called, and there was a failed attempt. Result: **`ADDRESS_NOT_UNDERSTOOD`**.

In the code this was the ADDRESS condition in `classify_events` in [classify.py](../classify.py). Any one of three things was enough for the label: a failed attempt, ≥ 2 attempts, or the call ended by the bot/`system`. A single failed attempt was enough whatever the value of `hangup.by`.

The basis was decision **B1** in [contested_cases.md](contested_cases.md): "after `no_match`/`ambiguous` the **caller** hung up (the bot had not given up yet) → `ADDRESS_NOT_UNDERSTOOD`". Its reasoning: there was an address failure, the person left without help, and per the README `ENDED_EARLY` applies only when no tool failed.

## Why `ENDED_EARLY` fits better

1. **The bot had not given up.** By the precedents, `ADDRESS_NOT_UNDERSTOOD` means the bot never established the address and gave up. On night 2, 240 other calls have this label. The bot ends all 240 (`hangup.by = bot`) after 2–3 attempts, and the last line is the same in every one: "Mrzí ma to, adresu sa mi nepodarilo overiť…". That line never appears in group A: the bot had just asked for the address again when the call dropped.

2. **A retry usually works.** Night 2 has 300 calls where the first attempt also failed but the connection held. In 180 of them (60 %) the address was found on a later attempt, and all 180 are `KNOWN_OUTAGE_INFORMED`. So we cannot say the bot "did not understand the address": in most similar cases it understands it on the second or third attempt. Recognition in those 300 calls is just as poor (mean `asr_conf` 0.58 vs. 0.53 in group A), so group A does not stand out as having especially hard addresses.

3. **The same scenario got different labels.** In both groups the connection dropped mid-dialogue while the bot was waiting for the caller. Group B got `ENDED_EARLY`, group A `ADDRESS_NOT_UNDERSTOOD`. The only difference was the status of the previous tool call. The 75 / 75 split looks like a deliberate check that the label depends on how the call ended, not on the step at which the connection dropped. This is my guess; only the leaderboard can confirm it.

4. **B1 was written for the caller, not the network.** B1 says explicitly that the **caller** hung up. The network was not considered: night 1 had no `network` value. The code applied B1 more broadly than it was decided, to any `hangup.by` except the bot. And B1 never fired on night 1: the bot ended all 456 `ADDRESS_NOT_UNDERSTOOD` calls. So B1 had never been tested on real data, and the first case where it fired was network drops.

5. **Wrong owner of the fix.** In the client report `ADDRESS_NOT_UNDERSTOOD` counts as "the bot or the resolver did not understand the address", which is work for our product team. But the cause here is the network. Even a perfect resolver would not have saved a call that dropped during the retry. These 75 calls inflated the address failures on night 2 from 240 to 315 (+31 %).

## The case for the old label

- The README describes `ENDED_EARLY` as a call that ended early without a tool failure, and `no_match` is formally a tool failure. Read literally, the old label was defensible.
- You accepted B1 in round 1 (`contested_cases.md`, the row "B1, B3–B6, B9–B11 ✅"). The proposal below does not revoke B1; it narrows it so that it does not extend to a dropped connection.

There is no ground truth for night 2, so only the leaderboard can settle it. Arguments 1–5 rest on the outcome for the caller, not on an intermediate status. That is the main principle of the assignment: the outcome for the caller decides, not intermediate failures.

## Independent check

An auditor subagent (Opus, effort high) wrote its own labeller from scratch. It matched `predictions_night1.csv` on all 11,400 night-1 calls and differed on night 2 in exactly these 75 calls. Its verdict: `ENDED_EARLY`, medium confidence. Caveat: my claim was in its brief, so on this point its check is not fully independent.

## What changes if accepted

| Label | Before | After |
|---|---:|---:|
| `ADDRESS_NOT_UNDERSTOOD` | 315 | 240 |
| `ENDED_EARLY` | 205 | 280 |

Night 1 does not change: it has no network drops, and B1 never fired there.

Time of day: the drops are spread over the whole night, 2.8–5.1 % of calls in each hour. The data shows no separate telephony outage window like the OMS degradation window on night 1.

## Proposed fix (not applied)

In §4.3 a single failed attempt is enough for `ADDRESS_NOT_UNDERSTOOD` only if the bot/`system` ended the call or the **caller** hung up (B1 as worded). Any other `hangup.by` value (`network` and future unknown ones) with one attempt and no bot give-up → `ENDED_EARLY`. The "≥ 2 attempts" and "the bot gave up" rules stay.

To avoid naming the network in the code, the set "who can leave on their own" is `{caller}`, and anything outside `{caller, bot, system}` counts as an external drop. A test for B1 + `network` and an entry in the specification change log are also needed.

## Decision (26. 11. 2026)

You decided more broadly than I proposed: **a network drop before any outcome is always `ENDED_EARLY`**. The number of attempts and earlier tool failures do not matter: it is a dropped connection, and neither the caller nor the bot ended the call. My proposal above with the "one attempt" condition was therefore not applied.

What was done (decision N1, specification ed. 7):
- [classify.py](../classify.py): if `hangup.by = network` and there was no outcome before the drop → `ENDED_EARLY`. This covers the address branch and `get_outage`/`create_ticket` failures. An outcome reached before the drop (transfer, ticket, reported status, `route`) keeps its label.
- Tests: 8 new `N1` cases in `tests/test_classify.py`, 91 in total, all pass. Labeled sample: 60/60.
- Night 1 matches `predictions_night1.csv` byte for byte: it has no `network` value.
- Night 2: exactly these 75 calls changed. Now `ADDRESS_NOT_UNDERSTOOD` 240, `ENDED_EARLY` 280. `noc2/predictions_night2.csv` (not committed) was regenerated.

The text above is kept unchanged as the record of the reasoning. Where it says "before N1" or describes the old label, it means the state before the decision.
