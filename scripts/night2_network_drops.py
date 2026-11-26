#!/usr/bin/env python3
"""Night 2: calls cut by the network (`hangup.by == "network"`).

    python scripts/night2_network_drops.py noc2/data/transcripts.jsonl noc2/data/calls.csv \
        --out docs/calls_network_drop_night2.md

Prints to stdout every number used in docs/night2_network_drop.md and writes a readable
dump of the calls (git-ignored: it contains the assignment's call data).
Groups:
  A  network drop right after the FIRST failed resolve_address (no_match/ambiguous),
     no get_outage call — today ADDRESS_NOT_UNDERSTOOD (spec 4.3, decision B1)
  B  network drop after a successful resolve_address, before get_outage — today ENDED_EARLY
Labels come from classify.py (single source of labels). Standard library only.
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from statistics import mean, median

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import classify  # noqa: E402
from render_labeled import fmt_event  # noqa: E402

LOCAL = timedelta(hours=1)  # Europe/Bratislava in November = UTC+1


def load(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                out.append(json.loads(ln))
    return out


def ev_of(c, kind, name=None):
    return [e for e in c["events"] if e.get("type") == kind and (name is None or e.get("name") == name)]


def hangup(c):
    return next((e for e in c["events"] if e.get("type") == "hangup"), {})


def first_caller_conf(c):
    cs = [e.get("asr_conf") for e in ev_of(c, "caller") if isinstance(e.get("asr_conf"), (int, float))]
    return cs[0] if cs else None


def group(c):
    if hangup(c).get("by") != "network":
        return None
    if ev_of(c, "tool_call", "get_outage"):
        return "other"
    rs = ev_of(c, "tool_result", "resolve_address")
    if len(rs) == 1 and rs[0].get("status") != "ok":
        return "A"
    if rs and rs[-1].get("status") == "ok":
        return "B"
    return "other"


def gap_before_hangup(c):
    """Seconds from the last non-hangup event to the hangup."""
    ev = c["events"]
    h = next(i for i, e in enumerate(ev) if e.get("type") == "hangup")
    return round(ev[h]["t"] - ev[h - 1]["t"], 1) if h > 0 else None


def rng(xs):
    xs = [x for x in xs if x is not None]
    return "%.1f / %.1f / %.1f" % (min(xs), median(xs), max(xs)) if xs else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcripts", nargs="?", default="noc2/data/transcripts.jsonl")
    ap.add_argument("calls_csv", nargs="?", default="noc2/data/calls.csv")
    ap.add_argument("--out", default="docs/calls_network_drop_night2.md")
    a = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass

    calls = load(a.transcripts)
    started = {r["call_id"]: r["started_at"] for r in csv.DictReader(open(a.calls_csv, encoding="utf-8"))}
    label = {c["call_id"]: classify.classify_call(c) for c in calls}
    grp = {c["call_id"]: group(c) for c in calls}
    A = [c for c in calls if grp[c["call_id"]] == "A"]
    B = [c for c in calls if grp[c["call_id"]] == "B"]

    p = print
    p("calls:", len(calls))
    p("hangup.by:", dict(Counter(hangup(c).get("by") for c in calls)))
    p("network groups:", dict(Counter(g for g in grp.values() if g)))
    for name, g in (("A", A), ("B", B)):
        p("group %s: %d calls, labels %s" % (name, len(g), dict(Counter(label[c["call_id"]] for c in g))))
        p("  resolve statuses:", dict(Counter(ev_of(c, "tool_result", "resolve_address")[-1]["status"] for c in g)))
        p("  last event before hangup:", dict(Counter(c["events"][[e.get("type") for e in c["events"]].index("hangup") - 1]["type"] for c in g)))
        p("  gap last event -> hangup, s (min/median/max):", rng([gap_before_hangup(c) for c in g]))
        p("  first caller asr_conf mean: %.2f" % mean(first_caller_conf(c) for c in g))
        last_bot = [ev_of(c, "bot")[-1]["text"] for c in g]
        if name == "B":  # address readbacks differ per call; show the shape only
            p("  last bot line is an address readback ending 'Sedí to?': %d" % sum(t.endswith("Sedí to?") for t in last_bot))
            p("  caller's last reply:", dict(Counter(ev_of(c, "caller")[-1]["text"] for c in g)))
        else:
            p("  last bot line:", dict(Counter(last_bot)))

    # all other ADDRESS_NOT_UNDERSTOOD calls: how did they end?
    anu = [c for c in calls if label[c["call_id"]] == "ADDRESS_NOT_UNDERSTOOD" and grp[c["call_id"]] != "A"]
    p("other ADDRESS_NOT_UNDERSTOOD: %d, hangup.by %s, resolve attempts %s" % (
        len(anu), dict(Counter(hangup(c).get("by") for c in anu)),
        dict(Counter(len(ev_of(c, "tool_call", "resolve_address")) for c in anu))))
    p("  last bot line starts:", dict(Counter(ev_of(c, "bot")[-1]["text"][:45] for c in anu)))

    # what happens after a failed FIRST attempt when the line holds
    fail1 = [c for c in calls if ev_of(c, "tool_result", "resolve_address")
             and ev_of(c, "tool_result", "resolve_address")[0].get("status") != "ok"
             and grp[c["call_id"]] != "A"]
    resolved = [c for c in fail1 if any(e.get("status") == "ok" for e in ev_of(c, "tool_result", "resolve_address"))]
    p("first attempt failed, line held: %d calls; address later found in %d (%.0f %%)" % (
        len(fail1), len(resolved), 100.0 * len(resolved) / len(fail1)))
    p("  their labels:", dict(Counter(label[c["call_id"]] for c in fail1)))
    p("  hangup.by:", dict(Counter(hangup(c).get("by") for c in fail1)))
    p("  first caller asr_conf mean: %.2f" % mean(first_caller_conf(c) for c in fail1))

    # time of day (local) of network drops vs all calls
    def hour(cid):
        return (datetime.strptime(started[cid], "%Y-%m-%dT%H:%M:%SZ") + LOCAL).hour
    allh = Counter(hour(c["call_id"]) for c in calls)
    neth = Counter(hour(c["call_id"]) for c in A + B)
    p("local hour: all calls / network drops (A+B)")
    for h in sorted(allh, key=lambda x: (x < 12, x)):
        p("  %02d:00  %5d  %3d  (%.1f %%)" % (h, allh[h], neth[h], 100.0 * neth[h] / allh[h]))

    # night 1: did a caller ever leave after a single failed attempt (decision B1)?
    n1 = os.path.join(ROOT, "data", "transcripts.jsonl")
    if os.path.exists(n1):
        n1c = load(n1)
        anu1 = [c for c in n1c if classify.classify_call(c) == "ADDRESS_NOT_UNDERSTOOD"]
        p("night 1 ADDRESS_NOT_UNDERSTOOD: %d, hangup.by %s" % (len(anu1), dict(Counter(hangup(c).get("by") for c in anu1))))

    # readable dump
    cmd = "python scripts/night2_network_drops.py %s %s --out %s" % (a.transcripts, a.calls_csv, a.out)
    out = ["# Night 2: calls cut by the network (`hangup.by = network`)", "",
           "Generated by: `%s`. Explanation: [night2_network_drop.md](night2_network_drop.md)." % cmd, "",
           "Times in the transcripts are seconds from the call start; `start` is local time (UTC+1).", "",
           "## Group A — %d calls: drop after the first failed address attempt" % len(A), "",
           "Label (classify.py): `%s`. Before decision N1: `ADDRESS_NOT_UNDERSTOOD`." % "/".join(sorted({label[c["call_id"]] for c in A})), "",
           "| call_id | start | what the caller said | asr_conf | resolver status | pause before the drop, s |",
           "|---|---|---|---:|---|---:|"]
    for c in A:
        cid = c["call_id"]
        said = ev_of(c, "tool_call", "resolve_address")[0].get("args", {}).get("text", "")
        st = ev_of(c, "tool_result", "resolve_address")[0].get("status")
        t = (datetime.strptime(started[cid], "%Y-%m-%dT%H:%M:%SZ") + LOCAL).strftime("%H:%M")
        out.append("| %s | %s | %s | %.2f | %s | %s |" % (cid, t, said.replace("|", "\\|"),
                                                       first_caller_conf(c), st, gap_before_hangup(c)))
    for c in A:
        out += ["", "### %s — %s" % (c["call_id"], label[c["call_id"]]), "", "```text"]
        out += [fmt_event(e) for e in c["events"]]
        out.append("```")
    out += ["", "## Group B — %d twin calls: drop after the address was found (for comparison)" % len(B), "",
            "Label (classify.py): `%s`. Unchanged." % "/".join(sorted({label[c["call_id"]] for c in B})), ""]
    for c in B:
        out += ["", "### %s — %s" % (c["call_id"], label[c["call_id"]]), "", "```text"]
        out += [fmt_event(e) for e in c["events"]]
        out.append("```")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print("%d + %d calls -> %s" % (len(A), len(B), a.out), file=sys.stderr)


if __name__ == "__main__":
    main()
