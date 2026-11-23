"""Data profile of one night: structural call patterns and the checks behind docs/contested_cases.md.

Usage: python scripts/profile_night.py [transcripts.jsonl] [calls.csv]
Stdlib only. Prints a plain-text report to stdout.
"""
import collections
import csv
import json
import statistics as st
import sys
from datetime import datetime, timedelta

C = collections.Counter


def signature(events):
    """Compact structural signature of a call (ignores bot/caller speech)."""
    out = []
    for e in events:
        t = e.get("type")
        if t == "tool_call":
            out.append("call:" + str(e.get("name")))
        elif t == "tool_result":
            tag = str(e.get("status"))
            r = e.get("result") or {}
            if e.get("name") == "get_outage" and tag == "ok":
                tag = "known" if r.get("outage_id") else "unknown"
            out.append(f"res:{e.get('name')}/{tag}")
        elif t == "transfer":
            out.append("transfer:" + str(e.get("status")))
        elif t == "route":
            out.append("route:" + str(e.get("target")))
        elif t == "hangup":
            out.append("hangup:" + str(e.get("by")))
    return " ".join(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    tpath = sys.argv[1] if len(sys.argv) > 1 else "data/transcripts.jsonl"
    cpath = sys.argv[2] if len(sys.argv) > 2 else "data/calls.csv"
    rows = list(csv.DictReader(open(cpath, encoding="utf-8")))
    meta = {r["call_id"]: r for r in rows}

    n = 0
    sigs, sig_ex = C(), {}
    types, statuses, transfers, routes, hangups = C(), C(), C(), C(), C()
    events_after_hangup = 0
    confirm_answers = C()
    no_tool_caller_text = C()
    late = []  # (wait_s, eventual status or None, local hour)
    stale_eta, known_total = C(), 0
    desc_is_bot_prompt, tickets = 0, 0
    asr_before_resolve = collections.defaultdict(list)
    speech_to_hangup = collections.defaultdict(list)

    for line in open(tpath, encoding="utf-8"):
        d = json.loads(line)
        n += 1
        ev = d["events"]
        cid = d["call_id"]
        start = datetime.fromisoformat(meta[cid]["started_at"].replace("Z", "+00:00"))
        s = signature(ev)
        sigs[s] += 1
        sig_ex.setdefault(s, cid)
        hang = [e for e in ev if e.get("type") == "hangup"]
        hi = ev.index(hang[-1]) if hang else len(ev)
        if hi < len(ev) - 1:
            events_after_hangup += 1

        for i, e in enumerate(ev):
            t = e.get("type")
            types[t] += 1
            if t == "tool_result":
                statuses[(e.get("name"), e.get("status"), "result" in e)] += 1
            elif t == "transfer":
                transfers[(e.get("target"), e.get("status"))] += 1
            elif t == "route":
                routes[e.get("target")] += 1
            elif t == "hangup":
                hangups[e.get("by")] += 1
            elif t == "bot" and "správne" in e.get("text", ""):
                nxt = next((x for x in ev[i + 1:] if x.get("type") in ("caller", "hangup", "tool_call")), None)
                if nxt and nxt.get("type") == "caller":
                    confirm_answers[nxt["text"]] += 1
            elif t == "caller":
                nxt = next((x for x in ev[i + 1:] if x.get("type") == "tool_result"), None)
                if nxt and nxt.get("name") == "resolve_address":
                    asr_before_resolve[nxt.get("status")].append(e.get("asr_conf", 0))

            # get_outage still pending when the call ended
            if t == "tool_call" and e.get("name") == "get_outage" and i < hi:
                res = next((x for x in ev[i + 1:] if x.get("type") == "tool_result" and x.get("name") == "get_outage"), None)
                if res is None or ev.index(res) > hi:
                    local_h = (start + timedelta(hours=1, seconds=e["t"])).strftime("%H")
                    late.append((round(ev[hi]["t"] - e["t"], 1), res.get("status") if res else None, local_h))

            if t == "tool_result" and e.get("status") == "ok" and i < hi:
                r = e.get("result") or {}
                known = e.get("name") == "get_outage" and r.get("outage_id")
                if known or e.get("name") == "create_ticket":
                    b = next((x for x in ev[i + 1:hi] if x.get("type") == "bot"), None)
                    if b:
                        speech_to_hangup[(e["name"], ev[hi].get("by"))].append(round(ev[hi]["t"] - b["t"], 1))
                if known:
                    known_total += 1
                    now = start + timedelta(seconds=e["t"])
                    eta = datetime.fromisoformat(r["eta"]) if r.get("eta") else None
                    if eta and eta < now:
                        stale_eta[eta.strftime("%H:%M")] += 1

            if t == "tool_call" and e.get("name") == "create_ticket":
                tickets += 1
                prev_bot = [x for x in ev[:i] if x.get("type") == "bot"]
                if prev_bot and (e.get("args") or {}).get("description") == prev_bot[-1].get("text"):
                    desc_is_bot_prompt += 1

        if all(e.get("type") in ("bot", "caller", "hangup") for e in ev):
            said = " / ".join(e["text"] for e in ev if e.get("type") == "caller")
            no_tool_caller_text[said or "<nič>"] += 1

    ended_by = C(r["ended_by"] for r in rows)
    callers = C(r["caller_hash"] for r in rows)

    print(f"calls in transcripts: {n}; rows in calls.csv: {len(rows)}")
    print(f"ended_by (calls.csv): {dict(ended_by)}  bot share = {ended_by['bot'] / len(rows):.1%}")
    print(f"flow_version: {dict(C(r['flow_version'] for r in rows))}")
    print(f"event types: {dict(types)}")
    print("tool_result (name, status, has_result):")
    for k, v in sorted(statuses.items(), key=lambda x: -x[1]):
        print(f"  {v:6d}  {k}")
    print(f"transfers: {dict(transfers)}")
    print(f"routes: {dict(routes)}")
    print(f"hangup.by: {dict(hangups)}")
    print(f"calls with events after hangup: {events_after_hangup}")

    print(f"\n== structural patterns ({len(sigs)}) ==")
    for k, v in sigs.most_common():
        print(f"{v:6d}  {sig_ex[k]}  {k}")

    print("\n== caller answers to address confirmation ==")
    for k, v in confirm_answers.most_common():
        print(f"{v:6d}  {k}")

    print("\n== calls with no tool/transfer/route: what caller said ==")
    for k, v in no_tool_caller_text.most_common():
        print(f"{v:6d}  {k}")

    print("\n== get_outage still pending when call ended ==")
    by_status = C(s for _, s, _ in late)
    print(f"  total {len(late)}; eventual status: {dict(by_status)}")
    for status in by_status:
        w = [x for x, s, _ in late if s == status]
        print(f"  {status}: wait before hangup min/median/max = {min(w)}/{st.median(w)}/{max(w)} s")
    print(f"  by local hour/status: {sorted(C((h, s) for _, s, h in late).items(), key=str)}")

    print("\n== bot status/ticket speech -> hangup gap (s) ==")
    for k, v in speech_to_hangup.items():
        print(f"  {k}: n={len(v)} min={min(v)} median={st.median(v)}")

    print(f"\n== stale ETA (eta earlier than moment of get_outage) == {sum(stale_eta.values())} / {known_total} known outages; by eta: {dict(stale_eta)}")
    print(f"== create_ticket description equals bot's previous prompt == {desc_is_bot_prompt} / {tickets}")

    print("\n== ASR confidence of the caller turn right before resolve_address ==")
    for k, v in asr_before_resolve.items():
        print(f"  {k}: n={len(v)} mean={st.mean(v):.3f} share<0.6={sum(a < 0.6 for a in v) / len(v):.1%}")

    rep = {h: c for h, c in callers.items() if c > 1}
    print(f"\n== callers == unique {len(callers)}; with >1 call {len(rep)}; calls from them {sum(rep.values())}; max calls by one {max(callers.values())}")

    round2(tpath, rows, meta)


# ---------------------------------------------------------------- round 2
# Checks added after the first review of docs/contested_cases.md.

TOWN_PARTS = ("grinava", "cajla", "kráľová", "harmónia", "limbach")
HELPED = {"KNOWN_OUTAGE_INFORMED", "TICKET_CREATED", "TRANSFERRED", "OUT_OF_SCOPE"}


def provisional_label(ev):
    """Structural label used only for profiling (matches labeled_sample 60/60).
    The real classifier is classify.py."""
    ty = [e.get("type") for e in ev]
    tr = [e for e in ev if e.get("type") == "transfer"]
    if tr:
        return "TRANSFERRED" if tr[-1].get("status") == "connected" else "TRANSFER_FAILED"
    if "route" in ty:
        return "OUT_OF_SCOPE"
    res = [e for e in ev if e.get("type") == "tool_result"]
    if any(e.get("name") == "create_ticket" and e.get("status") == "ok" for e in res):
        return "TICKET_CREATED"
    if any(e.get("name") == "create_ticket" for e in res):
        return "API_ERROR"
    hi = ty.index("hangup") if "hangup" in ty else len(ev)
    if any(e.get("type") == "tool_call" and e.get("name") == "get_outage" for e in ev):
        go = [e for e in res if e.get("name") == "get_outage"]
        if not go or go[-1].get("status") != "ok":
            return "API_ERROR"
        return "ENDED_EARLY" if ev.index(go[-1]) > hi else "KNOWN_OUTAGE_INFORMED"
    if "tool_call" in ty:
        return "ADDRESS_NOT_UNDERSTOOD"
    return "ENDED_EARLY"


def pct(a, b):
    return f"{a}/{b} ({a / b:.1%})" if b else f"{a}/0"


def round2(tpath, rows, meta):
    print("\n\n######## ROUND 2 ########")
    labels = {}
    sample_ok = 0
    for line in open("data/labeled_sample.jsonl", encoding="utf-8"):
        d = json.loads(line)
        sample_ok += provisional_label(d["events"]) == d["label"]
    print(f"provisional structural label vs labeled_sample: {sample_ok}/60")

    greet_silent_hang, halo_caller_t, halo_gap = [], [], []
    react = []
    stale_min, stale_by = [], C()
    attempts = []  # (status, asr, text)
    addr_fail_calls_best_asr = []
    bot_end_groups = C()
    bot_end_last_text = collections.defaultdict(C)
    transfer_wait, transfer_caller_during_wait, transfer_and_route = [], 0, 0
    transfer_failed_with_address = 0
    route_bot_text = C()
    last_bot_after_failed_transfer = C()

    for line in open(tpath, encoding="utf-8"):
        d = json.loads(line)
        ev = d["events"]
        cid = d["call_id"]
        lab = provisional_label(ev)
        labels[cid] = lab
        ty = [e.get("type") for e in ev]
        hang = [e for e in ev if e.get("type") == "hangup"]
        h = hang[-1] if hang else ev[-1]
        start = datetime.fromisoformat(meta[cid]["started_at"].replace("Z", "+00:00"))

        # A5/C4: calls with only speech
        if all(t in ("bot", "caller", "hangup") for t in ty):
            callers_said = [e for e in ev if e.get("type") == "caller"]
            if not callers_said:
                greet_silent_hang.append(h["t"])
            else:
                halo_caller_t.append(callers_said[0]["t"])
                halo_gap.append(round(h["t"] - callers_said[-1]["t"], 1))

        for i, e in enumerate(ev):
            t = e.get("type")
            # how fast the bot normally reacts to a caller turn
            if t == "caller":
                nxt = next((x for x in ev[i + 1:] if x.get("type") in ("bot", "tool_call", "transfer", "route", "hangup")), None)
                if nxt and nxt.get("type") != "hangup":
                    react.append(round(nxt["t"] - e["t"], 1))
            if t == "tool_call" and e.get("name") == "resolve_address":
                r = next((x for x in ev[i + 1:] if x.get("type") == "tool_result" and x.get("name") == "resolve_address"), None)
                c = [x for x in ev[:i] if x.get("type") == "caller"]
                attempts.append((r.get("status") if r else None, c[-1].get("asr_conf", 0) if c else 0, (e.get("args") or {}).get("text", "")))
            if t == "tool_result" and e.get("name") == "get_outage" and e.get("status") == "ok":
                r = e.get("result") or {}
                if r.get("outage_id") and r.get("eta"):
                    now = start + timedelta(seconds=e["t"])
                    eta = datetime.fromisoformat(r["eta"])
                    if eta < now:
                        stale_min.append((now - eta).total_seconds() / 60)
                        stale_by[h.get("by")] += 1

        if "tool_call" in ty and lab == "ADDRESS_NOT_UNDERSTOOD":
            res_ok = any(e.get("type") == "tool_result" and e.get("name") == "resolve_address" and e.get("status") == "ok" for e in ev)
            if not res_ok:
                asr_vals = [x.get("asr_conf", 0) for j, x in enumerate(ev) if x.get("type") == "caller"
                            and j + 1 < len(ev) and ev[j + 1].get("type") == "tool_call"]
                addr_fail_calls_best_asr.append(max(asr_vals) if asr_vals else 0)

        if h.get("by") == "bot":
            bot_end_groups[lab] += 1
            bots = [x for x in ev if x.get("type") == "bot"]
            bot_end_last_text[lab][bots[-1]["text"][:70] if bots else "-"] += 1

        if "transfer" in ty:
            i = ty.index("transfer")
            j = max((k for k in range(i) if ty[k] == "bot"), default=0)
            transfer_wait.append(round(ev[i]["t"] - ev[j]["t"], 1))
            transfer_caller_during_wait += "caller" in ty[j + 1:i]
            transfer_and_route += "route" in ty
            if lab == "TRANSFER_FAILED":
                transfer_failed_with_address += "tool_call" in ty
                bots = [x for x in ev if x.get("type") == "bot"]
                last_bot_after_failed_transfer[bots[-1]["text"]] += 1
        if "route" in ty:
            i = ty.index("route")
            if i and ev[i - 1].get("type") == "bot":
                route_bot_text[ev[i - 1]["text"]] += 1

    print(f"labels: {dict(C(labels.values()))}")

    print("\n== A5/C4 calls without tools ==")
    print(f"  caller silent: {len(greet_silent_hang)}; hangup t min/median/max = "
          f"{min(greet_silent_hang)}/{st.median(greet_silent_hang)}/{max(greet_silent_hang)} s")
    print(f"  caller said something: {len(halo_caller_t)}; spoke at t {min(halo_caller_t)}/{st.median(halo_caller_t)}/{max(halo_caller_t)} s; "
          f"caller->hangup {min(halo_gap)}/{st.median(halo_gap)}/{max(halo_gap)} s")
    p95 = sorted(react)[int(len(react) * 0.95)]
    print(f"  normal bot reaction to a caller turn: median {st.median(react)} s, p95 {p95} s, max {max(react)} s")
    print(f"  of those who spoke: hung up within normal median reaction {sum(g <= st.median(react) for g in halo_gap)}, "
          f"waited longer than p95 {sum(g > p95 for g in halo_gap)}")

    print("\n== C1 bot-ended calls by provisional label ==")
    tot = sum(bot_end_groups.values())
    for k, v in bot_end_groups.most_common():
        print(f"  {v:5d} {v / tot:6.1%}  {k}")
        for txt, n in bot_end_last_text[k].most_common(3):
            print(f"           {n:5d}  last bot: {txt}")

    print("\n== C2 stale ETA ==")
    s = sorted(stale_min)
    print(f"  {len(s)} calls; stale by min/median/max = {s[0]:.1f}/{s[len(s) // 2]:.1f}/{s[-1]:.1f} min; by hangup.by {dict(stale_by)}")

    print("\n== C5 ASR vs address ==")
    bins = [0, .5, .6, .7, .8, .9, 1.01]
    for status in ("ok", "no_match", "ambiguous"):
        v = [a for s_, a, _ in attempts if s_ == status]
        hist = [sum(bins[k] <= x < bins[k + 1] for x in v) for k in range(len(bins) - 1)]
        print(f"  {status:9s} n={len(v):5d}  asr <.5 | .5-.6 | .6-.7 | .7-.8 | .8-.9 | >=.9 : {hist}")
    fails = [(s_, a, t) for s_, a, t in attempts if s_ != "ok"]
    print(f"  failed attempts with asr < 0.8: {pct(sum(a < 0.8 for _, a, _ in fails), len(fails))}")
    b = addr_fail_calls_best_asr
    print(f"  ADDRESS_NOT_UNDERSTOOD calls without any ok resolve: {len(b)}; best attempt asr<0.8: {sum(a < 0.8 for a in b)}, >=0.8: {sum(a >= 0.8 for a in b)}")
    for part in TOWN_PARTS:
        okn = sum(part in t for s_, _, t in attempts if s_ == "ok")
        fn = sum(part in t for s_, _, t in attempts if s_ != "ok")
        print(f"  town part '{part}': attempts {okn + fn}, failed {pct(fn, okn + fn)}")
    allf = len(fails)
    print(f"  all attempts: failed {pct(allf, len(attempts))}")
    hi = [t for s_, a, t in fails if a >= 0.8]
    print(f"  failed attempts with asr>=0.8 mentioning a town part: {pct(sum(any(p in t for p in TOWN_PARTS) for t in hi), len(hi))}")

    print("\n== B16/C8 transfer and route ==")
    print(f"  bot 'connecting' -> transfer event wait: min/median/max = {min(transfer_wait)}/{st.median(transfer_wait)}/{max(transfer_wait)} s; "
          f"caller events during wait: {transfer_caller_during_wait}; transfer+route in one call: {transfer_and_route}")
    print(f"  TRANSFER_FAILED with an address already resolved: {transfer_failed_with_address}")
    for k, v in last_bot_after_failed_transfer.most_common():
        print(f"  last bot after failed transfer ({v}): {k}")
    for k, v in route_bot_text.most_common():
        print(f"  bot before route ({v}): {k}")

    print("\n== C7 repeat callers (provisional labels) ==")
    by = collections.defaultdict(list)
    for r in sorted(rows, key=lambda r: r["started_at"]):
        by[r["caller_hash"]].append(labels[r["call_id"]])
    rep = {k: v for k, v in by.items() if len(v) > 1}
    print(f"  repeaters: {len(rep)}")
    print(f"  helped only in the LAST call after an earlier non-help call: {sum(1 for v in rep.values() if v[-1] in HELPED and any(x not in HELPED for x in v[:-1]))}")
    print(f"  helped EARLIER, last call not help: {sum(1 for v in rep.values() if v[-1] not in HELPED and any(x in HELPED for x in v[:-1]))}")
    print(f"  never helped: {sum(1 for v in rep.values() if not any(x in HELPED for x in v))}")
    print(f"  last-call labels: {C(v[-1] for v in rep.values()).most_common()}")
    print(f"  non-help calls hidden by 'last call only': {sum(sum(x not in HELPED for x in v[:-1]) for v in rep.values())}")

    round5(tpath, meta)


def round5(tpath, meta):
    """Checks added after the spec review (sequential bot, hangups, get_outage consistency)."""
    print("\n\n######## ROUND 5 ########")
    hangups, overlap = C(), 0
    by_addr = collections.defaultdict(list)  # address_id -> [(start, outage_id or "")]
    by_outage = collections.defaultdict(list)  # outage_id -> [(start, eta)]
    for line in open(tpath, encoding="utf-8"):
        d = json.loads(line)
        ev = d["events"]
        start = datetime.fromisoformat(meta[d["call_id"]]["started_at"].replace("Z", "+00:00"))
        hangups[sum(e.get("type") == "hangup" for e in ev)] += 1
        pending = set()
        last_addr = None
        for e in ev:
            if e.get("type") == "tool_call":
                overlap += bool(pending)
                pending.add(e.get("name"))
                if e.get("name") == "get_outage":
                    last_addr = (e.get("args") or {}).get("address_id")
            elif e.get("type") == "tool_result":
                pending.discard(e.get("name"))
                if e.get("name") == "get_outage" and e.get("status") == "ok":
                    r = e.get("result") or {}
                    by_addr[last_addr].append((start, r.get("outage_id") or ""))
                    if r.get("outage_id"):
                        by_outage[r["outage_id"]].append((start, r.get("eta")))
    print(f"hangup events per call: {dict(hangups)}")
    print(f"tool_call issued while another tool result was pending: {overlap}")
    for win in (300, 900, 3600):
        n = diff = flip = 0
        for v in by_addr.values():
            v.sort(key=lambda x: x[0])
            for (t1, o1), (t2, o2) in zip(v, v[1:]):
                if (t2 - t1).total_seconds() <= win:
                    n += 1
                    diff += o1 != o2
                    flip += (o1 == "") != (o2 == "")
        print(f"same address_id re-queried within {win // 60:2d} min: {n} pairs; different outage_id {pct(diff, n)}; known<->unknown {pct(flip, n)}")
    n = diff = 0
    for v in by_outage.values():
        v.sort(key=lambda x: x[0])
        for (t1, e1), (t2, e2) in zip(v, v[1:]):
            if (t2 - t1).total_seconds() <= 600:
                n += 1
                diff += e1 != e2
    print(f"same outage_id, consecutive calls within 10 min: different ETA {pct(diff, n)}")


if __name__ == "__main__":
    main()
