#!/usr/bin/env python3
"""Task 2, bullet 1: what does the dashboard's "38 %" mean, and is the client right?

One command, deterministic, stdlib only. Prints every number used in docs/task2_38_percent.md.

    python scripts/task2_38_percent.py

Inputs (all from the repo): data/calls.csv, data/transcripts.jsonl, data/oms_api_metrics.txt,
predictions_night1.csv (output of classify.py; cross-checked against classify.classify_call).
Local time = Europe/Bratislava = UTC+1 on 15. 11. 2026 (fixed offset, no tz database needed).
"""
import csv
import datetime as dt
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", newline="")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

LOCAL = dt.timedelta(hours=1)
UTC = dt.timezone.utc
HELPED = ("KNOWN_OUTAGE_INFORMED", "TICKET_CREATED", "TRANSFERRED")
FAILED = ("API_ERROR", "ADDRESS_NOT_UNDERSTOOD", "TRANSFER_FAILED")
# loose match, display only (the split of bot-ended calls itself is by label / structure)
GOODBYE = re.compile(r"dovidenia|zbohom", re.I)


def p(path):
    return os.path.join(ROOT, *path.split("/"))


def pct(a, b):
    return "%.1f %%" % (100.0 * a / b) if b else "n/a"


def frac(a, b):
    return "%d/%d = %s" % (a, b, pct(a, b))


def head(s):
    print("\n" + "=" * 78 + "\n" + s + "\n" + "=" * 78)


def load():
    meta = {}
    with open(p("data/calls.csv"), encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            meta[r["call_id"]] = r
    lab = {}
    with open(p("predictions_night1.csv"), encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            lab[r["call_id"]] = r["label"]
    ev, raw = {}, {}
    with open(p("data/transcripts.jsonl"), encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                d = json.loads(ln)
                ev[d["call_id"]] = d["events"]
                raw[d["call_id"]] = d
    return meta, lab, ev, raw


def start(meta, c):
    return dt.datetime.strptime(meta[c]["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def loc_hms(meta, c, t=0.0):
    return (start(meta, c) + LOCAL + dt.timedelta(seconds=t)).strftime("%H:%M:%S")


def hangup_event(evs):
    h = [e for e in evs if e.get("type") == "hangup"]
    return h[0] if h else None  # first hangup = end of call (spec 4.0)


def last_bot_before_hangup(evs):
    h = hangup_event(evs)
    lim = h["t"] if h else float("inf")
    b = [e for e in evs if e.get("type") == "bot" and e["t"] <= lim]
    return b[-1] if b else None


def get_outage_final(evs):
    """(index, event) of the last get_outage tool_result, or (None, None)."""
    idx = [i for i, e in enumerate(evs) if e.get("type") == "tool_result" and e.get("name") == "get_outage"]
    return (idx[-1], evs[idx[-1]]) if idx else (None, None)


def status_utterance(evs):
    """bot event spoken right after the last (ok) get_outage result, or None."""
    i, r = get_outage_final(evs)
    if i is None:
        return None, None
    for e in evs[i + 1:]:
        if e.get("type") == "bot":
            return r, e
        if e.get("type") in ("tool_call", "tool_result", "hangup", "transfer", "route"):
            break
    return r, None


def eta_stale(meta, c, evs):
    """True/False/None: was the ETA already in the past at the moment the bot announced it?"""
    r, st = status_utterance(evs)
    if r is None or st is None:
        return None, None
    eta = (r.get("result") or {}).get("eta")
    if not eta:
        return None, None
    now = start(meta, c) + dt.timedelta(seconds=st["t"])
    d = dt.datetime.fromisoformat(eta)
    return d < now, (now - d).total_seconds() / 60.0


def main():
    meta, lab, ev, raw = load()
    ids = list(meta)
    N = len(ids)
    assert set(ids) == set(ev) == set(lab), "ids differ between calls.csv / transcripts / predictions"

    head("0. Inputs")
    print("calls.csv rows: %d, transcripts: %d, predictions: %d" % (N, len(ev), len(lab)))
    first = min(start(meta, c) for c in ids)
    last = max(start(meta, c) for c in ids)
    print("call starts (UTC): %s .. %s  = local %s .. %s" % (
        first.strftime("%H:%M:%S"), last.strftime("%H:%M:%S"),
        (first + LOCAL).strftime("%H:%M:%S"), (last + LOCAL).strftime("%H:%M:%S")))
    try:
        import classify  # cross-check: predictions_night1.csv == classify.py output
        mism = sum(1 for c in ids if classify.classify_call(raw[c]) != lab[c])
        print("cross-check classify.classify_call vs predictions_night1.csv: %d mismatches" % mism)
    except Exception as e:  # not fatal for this analysis
        print("cross-check skipped (%s)" % e)
    print("label totals:")
    for k, v in sorted(Counter(lab.values()).items(), key=lambda x: -x[1]):
        print("  %-24s %6d  %s" % (k, v, pct(v, N)))

    # ------------------------------------------------------------------ 1
    head("1. What the dashboard measures: ended_by in calls.csv")
    eb = Counter(meta[c]["ended_by"] for c in ids)
    for k, v in eb.most_common():
        print("  ended_by=%-8s %6d  %s" % (k, v, pct(v, N)))
    nbot = eb["bot"]
    print("=> dashboard '38 %%' = ended_by=bot = %s" % frac(nbot, N))
    mm = Counter()
    for c in ids:
        h = hangup_event(ev[c])
        mm[(meta[c]["ended_by"], h["by"] if h else "<none>")] += 1
    print("calls.csv ended_by vs transcript hangup.by (first hangup):")
    for k, v in sorted(mm.items(), key=lambda x: -x[1]):
        print("  csv=%-8s transcript=%-8s %6d%s" % (k[0], k[1], v, "" if k[0] == k[1] else "  <-- MISMATCH"))
    nh = Counter(sum(1 for e in ev[c] if e.get("type") == "hangup") for c in ids)
    print("hangup events per call:", dict(nh), "| mismatches:", sum(v for k, v in mm.items() if k[0] != k[1]))
    print("The dashboard counts WHO pressed the button, not WHETHER the caller got help.")

    # ------------------------------------------------------------------ 2
    head("2. What is inside ended_by=bot (%d calls)" % nbot)
    bot_ids = [c for c in ids if meta[c]["ended_by"] == "bot"]
    byl = Counter(lab[c] for c in bot_ids)
    print("by label:")
    for k, v in byl.most_common():
        print("  %-24s %5d  = %s of bot-ended, %s of all calls" % (k, v, pct(v, nbot), pct(v, N)))
    n_ok = byl["KNOWN_OUTAGE_INFORMED"]
    n_giveup = nbot - n_ok
    print("normal goodbye after status (label KNOWN_OUTAGE_INFORMED): %s of bot-ended; %s of all" % (frac(n_ok, nbot), pct(n_ok, N)))
    print("bot gave up (API_ERROR + ADDRESS_NOT_UNDERSTOOD + TRANSFER_FAILED): %s of bot-ended; %s of all" % (frac(n_giveup, nbot), pct(n_giveup, N)))
    print("any other label among bot-ended: %d" % sum(v for k, v in byl.items() if k not in ("KNOWN_OUTAGE_INFORMED",) + FAILED))

    print("\nlast bot sentence of bot-ended calls (digits -> #), grouped by label; goodbye? = loose match 'dovidenia|zbohom':")
    g = Counter()
    for c in bot_ids:
        b = last_bot_before_hangup(ev[c])
        t = re.sub(r"\d+", "#", b["text"]) if b else "<none>"
        g[(lab[c], bool(b and GOODBYE.search(b["text"])), t)] += 1
    for (l, gb, t), v in sorted(g.items(), key=lambda x: (-x[1], x[0])):
        print("  %5d  %-24s goodbye=%-5s %s" % (v, l, gb, t))

    print("\nDid the bot hang up silently? last event before hangup in bot-ended calls:")
    lastkind = Counter()
    gaps = defaultdict(list)
    for c in bot_ids:
        evs = ev[c]
        h = hangup_event(evs)
        before = [e for e in evs if e["t"] <= h["t"] and e is not h]
        lastkind[(lab[c] in FAILED, before[-1]["type"])] += 1
        b = last_bot_before_hangup(evs)
        gaps["failed" if lab[c] in FAILED else "goodbye"].append(h["t"] - b["t"])
    for k, v in sorted(lastkind.items()):
        print("  failure=%-5s last event before hangup = %-8s %5d" % (k[0], k[1], v))
    for k in ("goodbye", "failed"):
        x = gaps[k]
        print("  last bot sentence -> hangup gap, %-7s group: min %.1f / median %.1f / max %.1f s (n=%d)" % (
            k, min(x), statistics.median(x), max(x), len(x)))

    print("\nBot-ended failures by cause detail:")
    det = Counter()
    for c in bot_ids:
        l = lab[c]
        if l not in FAILED:
            continue
        evs = ev[c]
        if l == "API_ERROR":
            bad = [e for e in evs if e.get("type") == "tool_result" and e.get("name") in ("get_outage", "create_ticket") and e.get("status") != "ok"]
            det[(l, "%s %s" % (bad[-1]["name"], bad[-1]["status"]) if bad else "no tool result")] += 1
        elif l == "TRANSFER_FAILED":
            det[(l, "transfer " + [e for e in evs if e.get("type") == "transfer"][-1].get("status", "?"))] += 1
        else:
            n = sum(1 for e in evs if e.get("type") == "tool_call" and e.get("name") == "resolve_address")
            det[(l, "resolve_address attempts=%d" % n)] += 1
    for (l, d), v in sorted(det.items(), key=lambda x: (x[0][0], -x[1])):
        print("  %5d  %-24s %s" % (v, l, d))
    print("Note: the bot's give-up message always offered some next step (call later / voltika.sk form) but there is NO fallback in the flow (README).")

    # ------------------------------------------------------------------ 3
    head("3. Evidence that the 'normal goodbye' group is a success (%d calls)" % n_ok)
    good = [c for c in bot_ids if lab[c] == "KNOWN_OUTAGE_INFORMED"]
    seq = Counter()
    ctext = Counter()
    gap_hang = []
    ok_before = 0
    outage_with_id = 0
    for c in good:
        evs = ev[c]
        r, st = status_utterance(evs)
        if r and r.get("status") == "ok" and (r.get("result") or {}).get("outage_id"):
            outage_with_id += 1
        if st is not None:
            ok_before += 1
            i = evs.index(st)
            after = [e for e in evs[i + 1:]]
            seq[tuple(e["type"] for e in after)] += 1
            for e in after:
                if e["type"] == "caller":
                    ctext[e["text"]] += 1
            h = hangup_event(evs)
            gap_hang.append(h["t"] - st["t"])
    print("get_outage ok with non-null outage_id: %s" % frac(outage_with_id, len(good)))
    print("bot spoke immediately after that result (status/ETA announced): %s" % frac(ok_before, len(good)))
    print("event sequence after the status sentence:")
    for k, v in seq.most_common():
        print("  %5d  %s" % (v, " -> ".join(k)))
    print("caller replies after the status (all distinct texts):")
    for k, v in ctext.most_common():
        print("  %5d  %r" % (v, k))
    print("calls with a caller turn after the status sentence: %s; distinct reply texts: %d" % (frac(sum(ctext.values()), len(good)), len(ctext)))
    print("status sentence -> hangup: min %.1f / median %.1f / max %.1f s" % (min(gap_hang), statistics.median(gap_hang), max(gap_hang)))

    print("\nStale ETA (eta earlier than call start + t of the status sentence), KNOWN_OUTAGE_INFORMED only:")
    stale = defaultdict(lambda: [0, 0, []])
    for c in ids:
        if lab[c] != "KNOWN_OUTAGE_INFORMED":
            continue
        s, mins = eta_stale(meta, c, ev[c])
        k = meta[c]["ended_by"]
        stale[k][1] += 1
        if s:
            stale[k][0] += 1
            stale[k][2].append(mins)
    tot_s = tot_n = 0
    allm = []
    for k in ("bot", "caller"):
        a, b, m = stale[k]
        tot_s += a
        tot_n += b
        allm += m
        print("  ended_by=%-7s stale ETA %s" % (k, frac(a, b)))
    print("  total            stale ETA %s ; minutes past: median %.0f, max %.0f" % (frac(tot_s, tot_n), statistics.median(allm), max(allm)))
    print("  => in the 'normal goodbye' group the bot-ended calls with stale ETA: %d of %d; fresh ETA: %d" % (
        stale["bot"][0], stale["bot"][1], stale["bot"][1] - stale["bot"][0]))

    # ------------------------------------------------------------------ 4
    head("4. What the 38 % does NOT show: failures not ended by the bot")
    x = Counter((meta[c]["ended_by"], lab[c]) for c in ids)
    print("ended_by x label (failed + early):")
    for l in FAILED + ("ENDED_EARLY",):
        print("  %-24s bot=%5d caller=%5d system=%5d other=%d" % (
            l, x[("bot", l)], x[("caller", l)], x[("system", l)],
            sum(v for (e, ll), v in x.items() if ll == l and e not in ("bot", "caller", "system"))))
    ce = [c for c in ids if lab[c] == "API_ERROR" and meta[c]["ended_by"] != "bot"]
    waits, how = [], Counter()
    for c in ce:
        evs = ev[c]
        h = hangup_event(evs)
        gc = [e for e in evs if e.get("type") == "tool_call" and e.get("name") == "get_outage" and e["t"] <= h["t"]][-1]
        waits.append(h["t"] - gc["t"])
        _, r = get_outage_final(evs)
        how["get_outage result arrived AFTER hangup: " + r["status"] if r else "get_outage result never arrived"] += 1
        lb = last_bot_before_hangup(evs)
    print("API_ERROR where the caller hung up while waiting on get_outage: %d" % len(ce))
    for k, v in how.most_common():
        print("  %5d  %s" % (v, k))
    print("  wait get_outage call -> caller hangup: min %.1f / median %.1f / max %.1f s; bot said nothing while waiting" % (
        min(waits), statistics.median(waits), max(waits)))

    ee = [c for c in ids if lab[c] == "ENDED_EARLY"]
    sub = Counter()
    ew = []
    greet_t, filler_t = [], []
    for c in ee:
        evs = ev[c]
        tools = [e for e in evs if e.get("type") == "tool_call"]
        spoke = [e for e in evs if e.get("type") == "caller"]
        if any(e["name"] == "get_outage" for e in tools):
            k = "asked get_outage, caller hung up before the answer (answer ok came later)"
            h = hangup_event(evs)
            gc = [e for e in tools if e["name"] == "get_outage"][-1]
            ew.append(h["t"] - gc["t"])
        elif not spoke:
            k = "hung up in the greeting (caller said nothing)"
            greet_t.append(hangup_event(evs)["t"])
        elif not tools:
            k = "caller said one filler (halo/pocujete ma...), bot did not react, hung up"
            filler_t.append(hangup_event(evs)["t"] - spoke[-1]["t"])
        else:
            k = "other"
        sub[k] += 1
    print("\nENDED_EARLY (%d calls = %s of all), by structure:" % (len(ee), pct(len(ee), N)))
    for k, v in sub.most_common():
        print("  %5d  %s" % (v, k))
    print("  greeting group: hangup at t = %.1f..%.1f s (median %.1f); filler group: hangup %.1f..%.1f s after the caller's word (median %.1f)" % (
        min(greet_t), max(greet_t), statistics.median(greet_t), min(filler_t), max(filler_t), statistics.median(filler_t)))
    print("  wait in the 'asked get_outage' group: min %.1f / median %.1f / max %.1f s" % (min(ew), statistics.median(ew), max(ew)))
    print("  NB: ENDED_EARLY is 100 % caller-ended in the data (see table above), so the dashboard counts none of them as 'bot hung up'.")
    lat = [e["latency_ms"] / 1000.0 for c in ids for e in ev[c] if e.get("type") == "tool_result" and e.get("name") == "get_outage" and e.get("status") == "ok"]
    print("  for scale: get_outage ok latency median %.1f s, p95 %.1f s (all ok results, n=%d)" % (
        statistics.median(lat), sorted(lat)[int(0.95 * len(lat))], len(lat)))

    # ------------------------------------------------------------------ 5
    head("5. A meaningful metric: did the caller get help?")
    lc = Counter(lab.values())
    helped = sum(lc[l] for l in HELPED)
    failed = sum(lc[l] for l in FAILED)
    rows = [
        ("helped: status told / ticket created / dispatcher connected", helped,
         "KNOWN %d + TICKET %d + TRANSFERRED %d" % (lc["KNOWN_OUTAGE_INFORMED"], lc["TICKET_CREATED"], lc["TRANSFERRED"])),
        ("legitimately redirected (OUT_OF_SCOPE: customer line)", lc["OUT_OF_SCOPE"], ""),
        ("failed: API_ERROR / ADDRESS_NOT_UNDERSTOOD / TRANSFER_FAILED", failed,
         "API %d + ADDR %d + TRANSFER_FAILED %d" % (lc["API_ERROR"], lc["ADDRESS_NOT_UNDERSTOOD"], lc["TRANSFER_FAILED"])),
        ("caller left before the bot could help (ENDED_EARLY)", lc["ENDED_EARLY"], ""),
    ]
    tot = 0
    for name, v, d in rows:
        tot += v
        print("  %-62s %5d / %d = %s  %s" % (name, v, N, pct(v, N), d))
    print("  check sum = %d" % tot)
    print("\nComparison of candidate metrics (numerator / %d calls):" % N)
    f_bot = sum(1 for c in bot_ids if lab[c] in FAILED)
    f_not_bot = failed - f_bot
    print("  M1 dashboard: ended_by=bot                                  %s" % frac(nbot, N))
    print("  M2 bot hung up after giving up (bot-ended AND failed)       %s" % frac(f_bot, N))
    print("  M3 failed, whoever hung up (3 failure labels)               %s" % frac(failed, N))
    print("       of which NOT visible in the 38 %% (caller/system ended)  %s" % frac(f_not_bot, failed))
    print("       share of M3 that the bot-ended count catches            %s" % frac(f_bot, failed))
    print("  M4 M3 + ENDED_EARLY (no help of any kind)                   %s" % frac(failed + lc["ENDED_EARLY"], N))
    print("  M5 share of bot-ended calls that are NOT failures           %s" % frac(nbot - f_bot, nbot))
    print("  M6 not helped nor redirected (M4)                           %s ; helped+redirected %s" % (
        frac(N - helped - lc["OUT_OF_SCOPE"], N), frac(helped + lc["OUT_OF_SCOPE"], N)))
    ctr = Counter(lab[c] for c in ids if meta[c]["ended_by"] == "bot")
    print("  decomposition of 38.0 %% (points of all calls): normal goodbye %.1f + failures %.1f = %.1f" % (
        100.0 * ctr["KNOWN_OUTAGE_INFORMED"] / N, 100.0 * f_bot / N, 100.0 * nbot / N))

    # ------------------------------------------------------------------ 6
    head("6. By local hour (call start, Europe/Bratislava = UTC+1)")
    hrs = defaultdict(list)
    for c in ids:
        hrs[(start(meta, c) + LOCAL).hour].append(c)
    print("%-11s %6s | %8s %7s %9s | %-8s %7s | %6s %6s %6s | %7s %7s" % (
        "local hour", "calls", "botended", "%", "ok-bye %", "failed", "%", "API", "ADDR", "XFERF", "EARLY", "%"))
    order = sorted(hrs, key=lambda h: (h < 12, h))  # 19..23, then 0
    for h in order:
        cs = hrs[h]
        n = len(cs)
        b = sum(1 for c in cs if meta[c]["ended_by"] == "bot")
        lcs = Counter(lab[c] for c in cs)
        f = sum(lcs[l] for l in FAILED)
        gb = sum(1 for c in cs if meta[c]["ended_by"] == "bot" and lab[c] == "KNOWN_OUTAGE_INFORMED")
        print("%02d:00-%02d:59 %6d | %8d %7s %9s | %-8d %7s | %6d %6d %6d | %7d %7s" % (
            h, h, n, b, pct(b, n), pct(gb, n), f, pct(f, n), lcs["API_ERROR"], lcs["ADDRESS_NOT_UNDERSTOOD"], lcs["TRANSFER_FAILED"],
            lcs["ENDED_EARLY"], pct(lcs["ENDED_EARLY"], n)))
    print("hour = local hour; 00:00-00:59 local = 23:00-23:59 UTC. Calls per hour peak: %s" % (
        max(hrs, key=lambda h: len(hrs[h]))))

    # OMS degradation window from oms_api_metrics.txt (UTC 5-min buckets)
    deg = []
    with open(p("data/oms_api_metrics.txt"), encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("#") or not ln.strip():
                continue
            b, req, p50, p95, er = ln.split()
            if float(er.rstrip("%")) >= 10.0:
                deg.append(dt.datetime.strptime(b, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC))
    w0, w1 = min(deg), max(deg) + dt.timedelta(minutes=5)
    print("\nOMS degradation (buckets with error_rate >= 10 %%): %s .. %s UTC = %s .. %s local (%d buckets)" % (
        w0.strftime("%H:%M"), w1.strftime("%H:%M"), (w0 + LOCAL).strftime("%H:%M"), (w1 + LOCAL).strftime("%H:%M"), len(deg)))
    inw = [c for c in ids if w0 <= start(meta, c) < w1]
    outw = [c for c in ids if not (w0 <= start(meta, c) < w1)]
    for name, cs in (("inside window (call start)", inw), ("outside window", outw)):
        lcs = Counter(lab[c] for c in cs)
        b = sum(1 for c in cs if meta[c]["ended_by"] == "bot")
        f = sum(lcs[l] for l in FAILED)
        print("  %-28s calls %5d | bot-ended %s | failed %s | API_ERROR %s" % (
            name, len(cs), frac(b, len(cs)), frac(f, len(cs)), frac(lcs["API_ERROR"], len(cs))))

    ae = Counter((meta[c]["ended_by"], w0 <= start(meta, c) < w1) for c in ids if lab[c] == "API_ERROR")
    print("API_ERROR by (ended_by, call started inside window): %s" % dict(sorted(ae.items())))

    # ------------------------------------------------------------------ 7
    head("7. Evidence: call_ids to open in data/transcripts.jsonl")

    def pick(pred, n=1, skip=0):
        out = [c for c in ids if pred(c)]
        return out[skip:skip + n]

    def fresh_goodbye(c):
        return meta[c]["ended_by"] == "bot" and lab[c] == "KNOWN_OUTAGE_INFORMED" and eta_stale(meta, c, ev[c])[0] is False

    def lh(c):
        return (start(meta, c) + LOCAL).hour

    def in_win(c):
        return w0 <= start(meta, c) < w1

    def timeout_giveup(c):
        return meta[c]["ended_by"] == "bot" and lab[c] == "API_ERROR"

    picks = [
        ("A1 normal goodbye (calm hour, fresh ETA)", pick(lambda c: fresh_goodbye(c) and lh(c) == 19)),
        ("A2 normal goodbye (peak hour 22, fresh ETA)", pick(lambda c: fresh_goodbye(c) and lh(c) == 22)),
        ("A3 normal goodbye BUT stale ETA (>= 30 min past)", pick(lambda c: meta[c]["ended_by"] == "bot" and lab[c] == "KNOWN_OUTAGE_INFORMED" and (eta_stale(meta, c, ev[c])[1] or 0) >= 30)),
        ("B1 give-up: get_outage timeout inside OMS window", pick(lambda c: timeout_giveup(c) and in_win(c))),
        ("B2 give-up: address not understood", pick(lambda c: meta[c]["ended_by"] == "bot" and lab[c] == "ADDRESS_NOT_UNDERSTOOD")),
        ("B3 give-up: dispatch queue_full", pick(lambda c: meta[c]["ended_by"] == "bot" and lab[c] == "TRANSFER_FAILED")),
        ("C1 failure ended by caller: no get_outage result at all", pick(lambda c: lab[c] == "API_ERROR" and meta[c]["ended_by"] == "caller" and get_outage_final(ev[c])[0] is None)),
        ("C2 failure ended by caller: timeout arrived after hangup", pick(lambda c: lab[c] == "API_ERROR" and meta[c]["ended_by"] == "caller" and get_outage_final(ev[c])[0] is not None)),
        ("C3 ENDED_EARLY: caller left while waiting, ok answer came later", pick(lambda c: lab[c] == "ENDED_EARLY" and any(e.get("name") == "get_outage" for e in ev[c] if e.get("type") == "tool_call"))),
    ]
    for title, cs in picks:
        for c in cs:
            evs = ev[c]
            h = hangup_event(evs)
            lb = last_bot_before_hangup(evs)
            print("\n[%s] %s" % (title, c))
            print("  local start %s | label %s | ended_by %s (hangup t=%.1f s, duration_s=%s)" % (
                loc_hms(meta, c), lab[c], meta[c]["ended_by"], h["t"], meta[c]["duration_s"]))
            print("  last bot sentence (t=%.1f s): %s" % (lb["t"], lb["text"]))
            r, st = status_utterance(evs)
            if st is not None and r.get("status") == "ok":
                eta = (r.get("result") or {}).get("eta")
                stl, mins = eta_stale(meta, c, evs)
                print("  status said at t=%.1f s (local %s): %s | eta=%s | stale=%s%s" % (
                    st["t"], loc_hms(meta, c, st["t"]), st["text"], eta, stl, " (%.0f min past)" % mins if stl else ""))
            tail = [e for e in evs if e.get("type") in ("tool_call", "tool_result", "hangup", "transfer", "caller")][-4:]
            print("  tail events: " + " | ".join("%s%s t=%.1f%s" % (
                e["type"], ":" + str(e.get("name") or e.get("status") or e.get("by") or ""), e["t"],
                " status=" + e["status"] if e["type"] == "tool_result" else "") for e in tail))

    # ------------------------------------------------------------------ 8
    head("8. Caveat checks")
    tk = Counter()
    for c in ids:
        evs = ev[c]
        for i, e in enumerate(evs):
            if e.get("type") == "tool_call" and e.get("name") == "create_ticket":
                lb = [x for x in evs[:i] if x.get("type") == "bot"]
                tk[(e.get("args") or {}).get("description") == (lb[-1]["text"] if lb else None)] += 1
    print("create_ticket calls whose description == the bot's own previous sentence: %s" % frac(tk[True], sum(tk.values())))
    cnt = Counter(meta[c]["caller_hash"] for c in ids)
    print("unique caller_hash: %d; calls (not people) are the unit of every number here; hashes with >1 call: %d" % (
        len(cnt), sum(1 for v in cnt.values() if v > 1)))
    print("flow_version values:", dict(Counter(meta[c]["flow_version"] for c in ids)))


if __name__ == "__main__":
    main()
