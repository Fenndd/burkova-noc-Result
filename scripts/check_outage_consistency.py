"""Consistency of Voltika OMS get_outage answers on one night.

Usage:  python scripts/check_outage_consistency.py [data_dir]

Prints every number and evidence case used in docs/outage_consistency_evidence.md.
Deterministic (the permutation baseline uses a fixed seed). Standard library only.

Query time of a get_outage answer = calls.csv started_at (UTC) + t of the tool_result.
Times are printed in local time (Europe/Bratislava, UTC+1 in November).
"""
import collections
import csv
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone

LOCAL = timezone(timedelta(hours=1))
# OMS degradation window from oms_api_metrics.txt: buckets 20:40Z..21:30Z (incl. partial tail) -> 21:40-22:35 local
DEG_FROM = datetime(2026, 11, 15, 20, 40, tzinfo=timezone.utc)
DEG_TO = datetime(2026, 11, 15, 21, 35, tzinfo=timezone.utc)
SEED = 20261115
N_PERM = 20


def pct(a, b):
    return f"{a}/{b} ({100 * a / b:.1f} %)" if b else f"{a}/0"


def loc(t):
    return t.astimezone(LOCAL).strftime("%H:%M:%S")


def town_of(readback):
    m = re.search(r"Overím si:\s*(.*?),\s*(.*?)\.\s*Je", readback or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def base_town(town):
    return (town or "?").split(" – ")[0].split(" - ")[0].strip()


def load(data_dir):
    meta = {}
    with open(os.path.join(data_dir, "calls.csv"), encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            meta[r["call_id"]] = r
    queries = []  # one per get_outage tool_result with status ok
    n_calls = 0
    with open(os.path.join(data_dir, "transcripts.jsonl"), encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            n_calls += 1
            cid, ev = d["call_id"], d.get("events") or []
            m = meta.get(cid, {})
            start = datetime.fromisoformat(m.get("started_at", "2026-11-15T00:00:00Z").replace("Z", "+00:00"))
            readback, last_res, asked = {}, None, None
            for i, e in enumerate(ev):
                typ = e.get("type")
                if typ == "tool_result" and e.get("name") == "resolve_address" and (e.get("result") or {}).get("address_id"):
                    last_res = e["result"]["address_id"]
                elif typ == "bot" and "Overím" in (e.get("text") or "") and last_res:
                    readback.setdefault(last_res, e["text"])
                elif typ == "tool_call" and e.get("name") == "get_outage":
                    asked = (e.get("args") or {}).get("address_id")
                elif typ == "tool_result" and e.get("name") == "get_outage" and e.get("status") == "ok":
                    r = e.get("result") or {}
                    nxt = next((x for x in ev[i + 1:] if x.get("type") in ("bot", "hangup")), None)
                    said = nxt.get("text") if nxt and nxt.get("type") == "bot" else None
                    street, town = town_of(readback.get(asked))
                    queries.append(dict(
                        cid=cid, t=start + timedelta(seconds=float(e.get("t", 0))), a=asked,
                        o=r.get("outage_id"), eta=datetime.fromisoformat(r["eta"]) if r.get("eta") else None,
                        rb=readback.get(asked), street=street, town=town, said=said,
                        ch=m.get("caller_hash")))
    queries.sort(key=lambda q: (q["t"], q["cid"]))
    return n_calls, queries


def addr_pairs(queries, win):
    by_a = collections.defaultdict(list)
    for q in queries:
        by_a[q["a"]].append(q)
    out = []
    for v in by_a.values():
        for q1, q2 in zip(v, v[1:]):
            if (q2["t"] - q1["t"]).total_seconds() <= win:
                out.append((q1, q2))
    return out


def pair_stats(pairs):
    n = len(pairs)
    diff = sum(a["o"] != b["o"] for a, b in pairs)
    flip = sum((a["o"] is None) != (b["o"] is None) for a, b in pairs)
    both = [(a, b) for a, b in pairs if a["o"] and b["o"]]
    both_diff = sum(a["o"] != b["o"] for a, b in both)
    return n, diff, flip, len(both), both_diff


def outage_towns(queries):
    t = collections.defaultdict(set)
    a = collections.defaultdict(set)
    for q in queries:
        if q["o"]:
            t[q["o"]].add(base_town(q["town"]))
            a[q["o"]].add(q["a"])
    return t, a


def permuted(queries, rng):
    """Same queries (time, address, caller), answers (outage_id, eta) shuffled at random among them."""
    ans = [(q["o"], q["eta"]) for q in queries]
    rng.shuffle(ans)
    return [dict(q, o=o, eta=e) for q, (o, e) in zip(queries, ans)]


def summary_numbers(queries):
    n5, d5, f5, b5, bd5 = pair_stats(addr_pairs(queries, 300))
    t, _ = outage_towns(queries)
    multi = sum(len(v) > 1 for v in t.values())
    return dict(diff5=d5 / n5, flip5=f5 / n5, bothdiff5=bd5 / b5 if b5 else 0, multitown=multi / len(t),
                towns_mean=sum(len(v) for v in t.values()) / len(t))


def main():
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    data_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    n_calls, Q = load(data_dir)
    known = [q for q in Q if q["o"]]
    print(f"calls: {n_calls}; get_outage ok answers: {len(Q)}; known outage: {len(known)}; no outage: {len(Q) - len(known)}")
    print(f"answers not spoken (caller hung up before bot spoke): {sum(q['said'] is None for q in Q)}")

    # --- A. address identity -------------------------------------------------
    print("\n== A. Does address_id identify one address? ==")
    by_a = collections.defaultdict(list)
    for q in Q:
        by_a[q["a"]].append(q)
    rb_per_a = collections.Counter(len({q["rb"] for q in v}) for v in by_a.values())
    a_per_rb = collections.defaultdict(set)
    for q in Q:
        a_per_rb[q["rb"]].add(q["a"])
    print(f"address_ids queried: {len(by_a)}; with >=2 answers: {sum(len(v) > 1 for v in by_a.values())}")
    print(f"distinct read-back texts per address_id: {dict(rb_per_a)}")
    print(f"distinct address_ids per read-back text: {dict(collections.Counter(len(v) for v in a_per_rb.values()))}")
    print(f"missing read-back: {sum(q['rb'] is None for q in Q)}")

    # --- B. same address, re-queried -----------------------------------------
    print("\n== B. Same address_id, consecutive answers ==")
    for win in (120, 300, 900, 3600):
        n, d, f, b, bd = pair_stats(addr_pairs(Q, win))
        print(f"<= {win // 60:2d} min: pairs {n}; different answer {pct(d, n)}; known<->none flip {pct(f, n)}; "
              f"both known -> different outage_id {pct(bd, b)}")
    multi_a = [v for v in by_a.values() if len(v) >= 2]
    print(f"addresses with >=2 answers: {len(multi_a)}; of them got >=2 distinct answers all night: "
          f"{pct(sum(len({q['o'] for q in v}) > 1 for v in multi_a), len(multi_a))}")
    dist = collections.Counter(len({q["o"] for q in v if q["o"]}) for v in multi_a)
    print(f"distinct known outage_ids per address (addresses with >=2 answers): {dict(sorted(dist.items()))}")
    # known share per address vs. binomial expectation
    p = len(known) / len(Q)
    big = [v for v in by_a.values() if len(v) >= 8]
    allsame = sum(len({q["o"] is None for q in v}) == 1 for v in big)
    exp = sum(p ** len(v) + (1 - p) ** len(v) for v in big)
    print(f"global known share p={p:.3f}; addresses with >=8 answers: {len(big)}; all answers same kind "
          f"(all known or all none): observed {allsame}, expected if each answer independent ~{exp:.1f}")

    # --- C. restoration / new outage? -----------------------------------------
    print("\n== C. Restoration or new outage between queries? ==")
    pairs5 = addr_pairs(Q, 300)
    kn = [(a, b) for a, b in pairs5 if a["o"] and not b["o"]]
    nk = [(a, b) for a, b in pairs5 if not a["o"] and b["o"]]
    before_eta = sum(b["t"] < a["eta"] for a, b in kn if a["eta"])
    print(f"<=5 min known->none: {len(kn)}; second query BEFORE the first answer's ETA: {pct(before_eta, len(kn))}")
    print(f"<=5 min none->known: {len(nk)}")
    # A-B-A within 15 min on same address: known X, then other, then X again
    aba = 0
    tri = 0
    for v in by_a.values():
        for q1, q2, q3 in zip(v, v[1:], v[2:]):
            if (q3["t"] - q1["t"]).total_seconds() <= 900:
                tri += 1
                aba += q1["o"] is not None and q1["o"] == q3["o"] and q2["o"] != q1["o"]
    print(f"triples on same address within 15 min: {tri}; X -> other -> X again: {aba}")
    # ETA already in the past at query time
    past = sum(q["eta"] < q["t"] for q in known if q["eta"])
    print(f"known answers whose ETA is already in the past at query time: {pct(past, len(known))}")
    gaps = [(b["t"] - a["t"]).total_seconds() for a, b in pairs5 if a["o"] != b["o"]]
    gaps.sort()
    if gaps:
        print(f"gap of <=5 min pairs with different answers: median {gaps[len(gaps) // 2]:.0f} s, "
              f"<=60 s: {sum(g <= 60 for g in gaps)}")

    # --- D. ETA per outage_id --------------------------------------------------
    print("\n== D. ETA for the same outage_id ==")
    by_o = collections.defaultdict(list)
    for q in known:
        by_o[q["o"]].append(q)
    n = diff = up = down = 0
    for v in by_o.values():
        for q1, q2 in zip(v, v[1:]):
            if (q2["t"] - q1["t"]).total_seconds() <= 600 and q1["eta"] and q2["eta"]:
                n += 1
                if q1["eta"] != q2["eta"]:
                    diff += 1
                    up += q2["eta"] > q1["eta"]
                    down += q2["eta"] < q1["eta"]
    print(f"consecutive answers <=10 min: {n}; different ETA {pct(diff, n)} (later {up}, earlier {down})")
    multi_o = [v for v in by_o.values() if len(v) >= 3]
    mono = 0
    for v in multi_o:
        e = [q["eta"] for q in v]
        mono += all(x <= y for x, y in zip(e, e[1:])) or all(x >= y for x, y in zip(e, e[1:]))
    print(f"outage_ids with >=3 answers: {len(multi_o)}; ETA sequence monotonic over the night: {pct(mono, len(multi_o))}")
    eta_vals = collections.Counter(q["eta"].astimezone(LOCAL).strftime("%H:%M") for q in known if q["eta"])
    print(f"ETA values (local): {dict(sorted(eta_vals.items()))}")
    distinct_eta = collections.Counter(len({q["eta"] for q in v}) for v in by_o.values() if len(v) >= 2)
    print(f"distinct ETAs per outage_id (ids with >=2 answers): {dict(sorted(distinct_eta.items()))}")

    # --- E. towns per outage_id ------------------------------------------------
    print("\n== E. Geography of an outage_id ==")
    towns, addrs = outage_towns(Q)
    multi_t = sum(len(v) > 1 for v in towns.values())
    print(f"outage_ids: {len(towns)} (numeric range O-{min(int(o[2:]) for o in towns)}..O-{max(int(o[2:]) for o in towns)})")
    print(f"outage_ids seen in >1 town (sub-parts like 'Pezinok – Cajla' merged into the town): {pct(multi_t, len(towns))}")
    print(f"towns per outage_id: {dict(sorted(collections.Counter(len(v) for v in towns.values()).items()))}")
    print(f"answers per outage_id vs distinct addresses per outage_id: "
          f"{sum(len(v) for v in by_o.values())} answers, {sum(len(v) for v in addrs.values())} (outage,address) pairs")
    all_towns = sorted({base_town(q["town"]) for q in Q})
    print(f"towns in the data ({len(all_towns)}): {', '.join(all_towns)}")
    mal_sam = [o for o, v in towns.items() if {"Malacky", "Šamorín"} <= v]
    print(f"outage_ids reported both in Malacky and in Šamorín: {len(mal_sam)}")

    # --- F. OMS degradation window ---------------------------------------------
    print("\n== F. Inside vs outside OMS degradation window (21:40-22:35 local) ==")
    def in_deg(q):
        return DEG_FROM <= q["t"] < DEG_TO
    for name, sel in (("inside", lambda a, b: in_deg(a) and in_deg(b)),
                      ("outside", lambda a, b: not in_deg(a) and not in_deg(b))):
        ps = [(a, b) for a, b in pairs5 if sel(a, b)]
        n, d, f, b, bd = pair_stats(ps)
        print(f"<=5 min pairs {name}: {n}; different answer {pct(d, n)}; flip {pct(f, n)}; both known diff id {pct(bd, b)}")
    print("by local hour (<=5 min pairs, hour of the 2nd answer):")
    hours = collections.defaultdict(list)
    for a, b in pairs5:
        hours[b["t"].astimezone(LOCAL).hour].append((a, b))
    for h in sorted(hours, key=lambda h: (h < 12, h)):
        n, d, f, _, _ = pair_stats(hours[h])
        kshare = [q for q in Q if q["t"].astimezone(LOCAL).hour == h]
        print(f"  {h:02d}h: pairs {n:4d}; different {pct(d, n)}; flip {pct(f, n)}; "
              f"known share of all answers {pct(sum(bool(q['o']) for q in kshare), len(kshare))}")

    # --- G. same caller --------------------------------------------------------
    print("\n== G. Same caller (caller_hash), same address, answers actually spoken ==")
    by_ca = collections.defaultdict(list)
    for q in Q:
        if q["said"] and q["ch"]:
            by_ca[(q["ch"], q["a"])].append(q)
    rep = {k: v for k, v in by_ca.items() if len(v) >= 2}
    contra_kind = {k for k, v in rep.items() if len({q["o"] is None for q in v}) > 1}
    contra_eta = {k for k, v in rep.items() if len({q["eta"] for q in v if q["eta"]}) > 1}
    contra_any = contra_kind | contra_eta
    people = {k[0] for k in rep}
    print(f"callers who heard >=2 outage answers for the same address: {len(people)} ({len(rep)} caller/address combos)")
    print(f"  told 'outage' once and 'no outage' another time: {len({k[0] for k in contra_kind})}")
    print(f"  told two different ETAs: {len({k[0] for k in contra_eta})}")
    print(f"  told contradictory things (either): {len({k[0] for k in contra_any})}")
    gaps_c = sorted((v[1]["t"] - v[0]["t"]).total_seconds() / 60 for k, v in rep.items() if k in contra_any)
    if gaps_c:
        print(f"  minutes between first two answers (contradictory callers): median {gaps_c[len(gaps_c) // 2]:.1f}")
    by_c = collections.defaultdict(list)
    for q in Q:
        if q["ch"]:
            by_c[q["ch"]].append(q)
    rc = {h: v for h, v in by_c.items() if len(v) >= 2}
    print(f"callers (caller_hash) with >=2 get_outage answers in different calls: {len(rc)}; "
          f"of them ever gave the same address_id twice: {sum(len({q['a'] for q in v}) < len(v) for v in rc.values())}; "
          f"gave addresses in >=2 different towns: {sum(len({base_town(q['town']) for q in v}) > 1 for v in rc.values())}")
    print("Different people, same address (answers actually spoken):")
    sp = collections.defaultdict(list)
    for q in Q:
        if q["said"]:
            sp[q["a"]].append(q)
    sp2 = {a: v for a, v in sp.items() if len(v) >= 2}
    ck = {a for a, v in sp2.items() if len({q["o"] is None for q in v}) > 1}
    ce = {a for a, v in sp2.items() if len({q["eta"] for q in v if q["eta"]}) > 1}
    print(f"  addresses with >=2 spoken answers: {len(sp2)} ({sum(len(v) for v in sp2.values())} calls)")
    print(f"  of them heard both 'outage' and 'no outage': {pct(len(ck), len(sp2))} ({sum(len(sp[a]) for a in ck)} calls)")
    print(f"  of them heard >=2 different ETAs: {pct(len(ce), len(sp2))}")
    print(f"  either: {pct(len(ck | ce), len(sp2))} ({sum(len(sp[a]) for a in ck | ce)} calls)")

    # --- G2. structure: neighbours and persistence ----------------------------
    print("\n== G2. Structure: does an answer persist, do neighbours share an outage? ==")
    trans = collections.Counter()
    for v in by_a.values():
        for q1, q2 in zip(v, v[1:]):
            trans[(q1["o"] is not None, q2["o"] is not None)] += 1
    kk, kn_ = trans[(True, True)], trans[(True, False)]
    nk_, nn = trans[(False, True)], trans[(False, False)]
    print(f"consecutive answers on same address (any gap): P(known | previous known) = {pct(kk, kk + kn_)}; "
          f"P(known | previous none) = {pct(nk_, nk_ + nn)}; unconditional {p:.3f}")
    street = collections.defaultdict(list)
    for q in known:
        street[(q["street"].rsplit(" ", 1)[0] if q["street"] else "?", q["town"])].append(q)
    n = same = 0
    for v in street.values():
        for i, q1 in enumerate(v):
            for q2 in v[i + 1:]:
                if q2["a"] != q1["a"] and (q2["t"] - q1["t"]).total_seconds() <= 900:
                    n += 1
                    same += q1["o"] == q2["o"]
                elif (q2["t"] - q1["t"]).total_seconds() > 900:
                    break
    print(f"two different addresses on the same street & town, both 'known', within 15 min: {n} pairs; "
          f"same outage_id {pct(same, n)}")

    # --- H. random baseline ------------------------------------------------------
    print(f"\n== H. Baseline: answers shuffled at random across all queries ({N_PERM} shuffles, seed {SEED}) ==")
    obs = summary_numbers(Q)
    rng = random.Random(SEED)
    sims = [summary_numbers(permuted(Q, rng)) for _ in range(N_PERM)]
    for k, label in (("diff5", "<=5 min same address: different answer"),
                     ("flip5", "<=5 min same address: known<->none flip"),
                     ("bothdiff5", "<=5 min both known: different outage_id"),
                     ("multitown", "outage_ids in >1 town"),
                     ("towns_mean", "mean towns per outage_id")):
        vals = sorted(s[k] for s in sims)
        fmt = (lambda x: f"{x:.2f}") if k == "towns_mean" else (lambda x: f"{100 * x:.1f} %")
        print(f"  {label:45s} observed {fmt(obs[k])}; shuffled min..max {fmt(vals[0])}..{fmt(vals[-1])}")

    # --- I. evidence cases -------------------------------------------------------
    print("\n== I. Evidence cases ==")

    def show(q):
        e = q["eta"].astimezone(LOCAL).strftime("%H:%M") if q["eta"] else "-"
        print(f"   {q['cid']}  {loc(q['t'])}  {q['a']}  [{q['rb']}]  outage={q['o']}  eta={e}  caller={q['ch']}")
        print(f"      bot: {q['said'] or '(caller hung up before the bot spoke)'}")

    def pick(cands, k, key):
        return sorted(cands, key=key)[:k]

    spoken = [(a, b) for a, b in pairs5 if a["said"] and b["said"]]
    print("\n-- I1. same address, both 'known', different outage_id, shortest gaps")
    for a, b in pick([(a, b) for a, b in spoken if a["o"] and b["o"] and a["o"] != b["o"]], 3,
                     key=lambda p: ((p[1]["t"] - p[0]["t"]).total_seconds(), p[0]["cid"])):
        print(f" gap {(b['t'] - a['t']).total_seconds():.0f} s"); show(a); show(b)
    print("\n-- I2. same address, 'known' then 'no outage' before the first ETA, shortest gaps")
    for a, b in pick([(a, b) for a, b in spoken if a["o"] and not b["o"] and b["t"] < a["eta"]], 3,
                     key=lambda p: ((p[1]["t"] - p[0]["t"]).total_seconds(), p[0]["cid"])):
        print(f" gap {(b['t'] - a['t']).total_seconds():.0f} s"); show(a); show(b)
    print("\n-- I3. same caller, same address, contradictory answers (shortest gaps)")
    for k in pick(list(contra_kind), 3, key=lambda k: ((rep[k][1]["t"] - rep[k][0]["t"]).total_seconds(), k)):
        print(f" caller {k[0]}")
        for q in rep[k]:
            show(q)
    if not contra_kind:
        print(" none exist; repeat callers instead (caller with most answers, then next):")
        for h in sorted(rc, key=lambda h: (-len(rc[h]), h))[:2]:
            print(f" caller {h}")
            for q in rc[h]:
                show(q)
    print("\n-- I3b. one address, different people, spoken answers (address with most spoken answers)")
    best = sorted(sp2, key=lambda a: (-len(sp2[a]), a))[0]
    for q in sp2[best]:
        show(q)
    print("\n-- I4. one outage_id in Malacky and Šamorín (first 2 by id)")
    for o in sorted(mal_sam)[:2]:
        print(f" {o}: towns {sorted(towns[o])}")
        for q in by_o[o]:
            show(q)
    print("\n-- I5. same outage_id, ETA jumps back and forth within minutes")
    shown = 0
    for o in sorted(by_o):
        v = by_o[o]
        for q1, q2, q3 in zip(v, v[1:], v[2:]):
            if (q3["t"] - q1["t"]).total_seconds() <= 900 and q1["eta"] == q3["eta"] != q2["eta"]:
                print(f" {o}"); show(q1); show(q2); show(q3)
                shown += 1
                break
        if shown >= 2:
            break


if __name__ == "__main__":
    main()
