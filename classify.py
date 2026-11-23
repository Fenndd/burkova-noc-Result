#!/usr/bin/env python3
"""Burkova noc, task 1: classify every call into exactly one outcome label.

Usage:
    python classify.py data/transcripts.jsonl [--out predictions.csv]

Output: CSV `call_id,label`, one row per non-empty input line, in input order
(stdout when --out is omitted). Diagnostics and the label summary go to stderr.

Implements docs/spec_task1_eval.md (edition 5); comments cite spec sections and
decision ids (A*, B*, R*, S04) from docs/contested_cases.md.
Only structured events are used; bot text is never matched (only "the bot spoke").
Standard library only, Python 3.8+.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict

LABELS = [
    "KNOWN_OUTAGE_INFORMED", "TICKET_CREATED", "TRANSFERRED", "TRANSFER_FAILED",
    "API_ERROR", "ADDRESS_NOT_UNDERSTOOD", "OUT_OF_SCOPE", "ENDED_EARLY",
]
FALLBACK = "KNOWN_OUTAGE_INFORMED"  # 5.2 item 6 (only for unrecoverable data)

# B14: the known scenario. Everything else (tools, event types) is ignored.
KNOWN_TOOLS = ("resolve_address", "get_outage", "create_ticket")
SCENARIO_KINDS = ("bot", "tool_call", "tool_result", "transfer", "route", "hangup")
BOT_ENDED = ("bot", "system")  # R5 / B13
SORT_RANK = {"tool_call": 0, "tool_result": 1, "transfer": 1}  # 5.2 item 3 tie-break (unsorted input only)

# Values seen on night 1; anything else is reported in the stderr summary (6, 4d).
NIGHT1_KNOWN = {
    "event type": {"bot", "caller", "tool_call", "tool_result", "transfer", "route", "hangup"},
    "tool name": set(KNOWN_TOOLS),
    "status resolve_address": {"ok", "no_match", "ambiguous"},
    "status get_outage": {"ok", "timeout"},
    "status create_ticket": {"ok", "timeout"},
    "hangup.by": {"caller", "bot", "system"},
    "transfer.status": {"connected", "queue_full", "timeout"},
    "route.target": {"customer_line"},
    "flow_version": {"v14"},
    "ended_by": {"caller", "bot", "system"},
}


# ---------------------------------------------------------------- small helpers

def norm(v):
    """Open-set strings are compared after strip().lower() (4.0)."""
    return "" if v is None else str(v).strip().lower()


def to_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN -> missing


def nonempty(v):
    if isinstance(v, str):
        return bool(v.strip())
    return v is not None and v is not False and v != [] and v != {}  # a boolean false is no id


def infer_kind(e):
    """5.2 item 2: type from fields when `type` is missing. Anything else stays unknown."""
    t = e.get("type")
    if isinstance(t, str) and t.strip():
        return t.strip().lower()
    if "args" in e:
        return "tool_call"
    if "name" in e and "status" in e:
        return "tool_result"
    if "by" in e:
        return "hangup"
    if "asr_conf" in e:
        return "caller"
    if "target" in e and "status" in e:
        return "transfer"
    if "target" in e:
        return "route"
    if "text" in e:  # typeless line with text and no asr_conf: the bot speaking
        return "bot"
    return ""


# ---------------------------------------------------------------- 4.0 preprocessing

def normalize_events(raw, notes):
    """Dict events -> flat records; missing t = previous t; stable sort by t (4.0)."""
    evs = []
    prev = 0.0
    for e in raw:
        if not isinstance(e, dict):
            notes.add("non-dict event skipped")
            continue
        kind = infer_kind(e)
        if kind != norm(e.get("type")):
            notes.add("event type inferred from fields")
        t = to_float(e.get("t"))
        if t is None:
            t = prev
            notes.add("event t missing/invalid")
        prev = t
        evs.append({
            "kind": kind, "t": t,
            "name": norm(e.get("name")), "status": norm(e.get("status")),
            "by": norm(e.get("by")), "target": norm(e.get("target")),
            "result": e.get("result"),
        })
    if any(a["t"] > b["t"] for a, b in zip(evs, evs[1:])):
        # 5.2 item 3: only unsorted input is re-sorted; equal t is then ordered causally
        # (call < result/transfer < the rest). Sorted input keeps file order exactly.
        evs.sort(key=lambda x: (x["t"], SORT_RANK.get(x["kind"], 2)))
    return evs


def call_limit(evs):
    """R2: the call ends at the FIRST hangup; later events are 'late'.
    Returns (limit, ended_by): events with index < limit happened during the call."""
    for i, e in enumerate(evs):
        if e["kind"] == "hangup":
            return i, e["by"]
    return len(evs), ""  # no hangup -> end = last event


def is_scenario(e):
    k = e["kind"]
    if k in ("tool_call", "tool_result"):
        return e["name"] in KNOWN_TOOLS
    return k in SCENARIO_KINDS


def next_scenario(evs, i):
    """First known-scenario event after i, skipping caller and unknown events (4.0)."""
    for j in range(i + 1, len(evs)):
        if evs[j]["kind"] != "caller" and is_scenario(evs[j]):
            return j
    return None


def bot_spoke_after(evs, i, limit):
    """4.0: the bot speaks right after the result, before the end of the call."""
    j = next_scenario(evs, i)
    return j is not None and j < limit and evs[j]["kind"] == "bot"


def build_attempts(evs, limit):
    """R3: the bot is sequential; the result of a call is the next result of the same tool.
    Calls placed after the hangup are ignored, except a create_ticket call (decision B): the
    ticket may still exist; such attempts carry late=True and only count as a TICKET_CREATED episode."""
    attempts, pending = [], {}
    for i, e in enumerate(evs):
        if e["name"] not in KNOWN_TOOLS:
            continue
        if e["kind"] == "tool_call":
            late = i >= limit
            if late and (e["name"] != "create_ticket" or e["name"] in pending):
                continue  # caller is gone; a late ticket call never steals an earlier call's result
            a = {"name": e["name"], "call": i, "res": None, "status": "", "result": None, "late": late}
            attempts.append(a)
            pending[e["name"]] = a
        elif e["kind"] == "tool_result":
            a = pending.pop(e["name"], None)
            if a is None:
                if i >= limit:
                    continue
                a = {"name": e["name"], "call": None, "res": None, "status": "", "result": None,
                     "late": False}
                attempts.append(a)
            a["res"], a["status"], a["result"] = i, e["status"], e["result"]
    return attempts


# ---------------------------------------------------------------- 5.1 success by evidence

def payload(a):
    return a["result"] if isinstance(a["result"], dict) else {}


def later_call(evs, i, name, limit):
    for j in range(i + 1, limit):
        if evs[j]["kind"] == "tool_call" and evs[j]["name"] == name:
            return True
    return False


def is_success(a, evs, limit):
    """Known success is `ok`; any other status only counts with payload AND flow continuation."""
    if a["res"] is None:
        return False
    if a["status"] == "ok":
        return True  # SPEC-AMBIGUITY: `ok` is success whatever the payload (5.1 "only ok is known success")
    i, p, name = a["res"], payload(a), a["name"]
    if i >= limit:
        return False  # non-ok result after the end cannot have been followed by the flow
    if name == "resolve_address":
        if not nonempty(p.get("address_id")):
            return False
        for j in range(i + 1, limit):  # next known call must be get_outage
            if evs[j]["kind"] == "tool_call" and evs[j]["name"] in KNOWN_TOOLS:
                return evs[j]["name"] == "get_outage"
        return False
    if name == "get_outage":
        if nonempty(p.get("outage_id")):
            return bot_spoke_after(evs, i, limit) and not later_call(evs, i, "get_outage", limit)
        if "outage_id" in p and p["outage_id"] is None:  # "no outage": flow must take that branch
            for j in range(i + 1, limit):
                e = evs[j]
                if e["kind"] == "transfer" or (e["kind"] == "tool_call" and e["name"] == "create_ticket"):
                    return True
        return False
    if name == "create_ticket":
        return (nonempty(p.get("ticket_id")) and bot_spoke_after(evs, i, limit)
                and not later_call(evs, i, "create_ticket", limit))
    return False


def outage_outcome(a, evs, limit):
    """What a get_outage attempt meant for the caller."""
    if not is_success(a, evs, limit):
        return "FAIL"
    if a["res"] >= limit:
        return "LATE_OK"  # A1: result after hangup, caller heard nothing
    if nonempty(payload(a).get("outage_id")):
        return "KNOWN_SPOKEN" if bot_spoke_after(evs, a["res"], limit) else "KNOWN_SILENT"  # B12
    # SPEC-AMBIGUITY: `ok` without an outage_id key (or non-dict result) is read as "no known outage".
    return "UNKNOWN"


def outage_known_before(ticket, attempts, evs, limit):
    """Decision A: a successful get_outage with a non-null outage_id earlier in the call."""
    ref = ticket["call"] if ticket["call"] is not None else ticket["res"]
    return any(a["name"] == "get_outage" and a["res"] is not None and a["res"] < ref
               and is_success(a, evs, limit) and nonempty(payload(a).get("outage_id"))
               for a in attempts)


def address_failed(resolves, evs, limit):
    """A failed resolve attempt, or no result at all (4.3)."""
    return any(not is_success(a, evs, limit) for a in resolves)


# ---------------------------------------------------------------- 4.2 route and R6

def unfixed_failure_before(pos, attempts, evs, limit):
    """R6: was there a failure before `pos` that was never fixed (4.0 definition)?
    Results arriving at/after `pos` count as missing."""
    before = [a for a in attempts if a["call"] is None or a["call"] < pos]

    def good(a):  # result existed before pos and was a success
        return a["res"] is not None and a["res"] < pos and is_success(a, evs, limit)

    tks = [a for a in before if a["name"] == "create_ticket"]  # furthest stage first (4.3)
    if tks:
        return not good(tks[-1])
    gos = [a for a in before if a["name"] == "get_outage"]
    if gos:
        a = gos[-1]
        return not (good(a) and outage_outcome(a, evs, limit) in ("KNOWN_SPOKEN", "UNKNOWN"))
    rs = [a for a in before if a["name"] == "resolve_address"]
    # SPEC-AMBIGUITY: "address not established" before a route uses the same test as 4.3
    # (a failed attempt or >= 2 attempts, no get_outage); the hangup.by part cannot apply here.
    return bool(rs) and (len(rs) >= 2 or any(not good(a) for a in rs))


# ---------------------------------------------------------------- 4.1 - 4.4 classification

def classify_events(evs):
    limit, ended_by = call_limit(evs)

    # 4.1 step 1: the LAST transfer before the end decides (B6, B9, B16, B17, S04, R7).
    transfers = [e for e in evs[:limit] if e["kind"] == "transfer"]
    if transfers:
        return "TRANSFERRED" if transfers[-1]["status"] == "connected" else "TRANSFER_FAILED"

    everything = build_attempts(evs, limit)
    attempts = [a for a in everything if not a["late"]]

    # 4.2 step 2: final episodes; the last one wins (B16).
    episodes = []  # (position, label)
    for a in everything:
        if a["name"] == "create_ticket" and is_success(a, evs, limit):
            # B3: the result may arrive after the hangup; decision B: so may the whole call.
            # Decision A: a ticket is an episode only while the outage was unknown.
            if not outage_known_before(a, attempts, evs, limit):
                episodes.append((a["res"], "TICKET_CREATED"))
        elif a["late"]:
            continue
        elif a["name"] == "get_outage" and outage_outcome(a, evs, limit) == "KNOWN_SPOKEN":
            episodes.append((a["res"], "KNOWN_OUTAGE_INFORMED"))  # B11: eta not required
    for i in range(limit):
        if evs[i]["kind"] == "route" and not unfixed_failure_before(i, attempts, evs, limit):
            episodes.append((i, "OUT_OF_SCOPE"))  # B10 (any target), R6
    if episodes:
        return max(episodes, key=lambda x: x[0])[1]

    # 4.3 step 3: no episode -> the last unfixed failure (the furthest stage) decides.
    tickets = [a for a in attempts if a["name"] == "create_ticket"]
    if tickets:
        return "API_ERROR"  # B4: ticket failed / no result (a success would be an episode)
    outages = [a for a in attempts if a["name"] == "get_outage"]
    if outages:
        o = outage_outcome(outages[-1], evs, limit)
        if o in ("FAIL", "KNOWN_SILENT"):  # A1, B12
            return "API_ERROR"
        if o == "LATE_OK":  # A1
            return "ENDED_EARLY"
        if o == "UNKNOWN" and ended_by in BOT_ENDED:  # B13 (B2 otherwise -> ENDED_EARLY)
            return "API_ERROR"
        return "ENDED_EARLY"
    resolves = [a for a in attempts if a["name"] == "resolve_address"]
    if resolves and (address_failed(resolves, evs, limit) or len(resolves) >= 2
                     or ended_by in BOT_ENDED):  # A2, B1, B8, R5; attempt count not hard-coded
        return "ADDRESS_NOT_UNDERSTOOD"

    # 4.4 step 4: everything else (A5, B2, R7, ...).
    return "ENDED_EARLY"


def classify_raw_events(raw, notes=None):
    """Raw event list -> label. Unusable input raises ValueError (caller falls back)."""
    notes = notes if notes is not None else set()
    if not isinstance(raw, list):
        raise ValueError("events is not a list")
    evs = normalize_events(raw, notes)
    if not evs:
        raise ValueError("no usable events")
    return classify_events(evs), evs


def classify_call(obj):
    """Public helper for tests: parsed call dict -> label (fallback on bad data)."""
    try:
        return classify_raw_events(obj.get("events"))[0]
    except Exception:
        return FALLBACK


# ---------------------------------------------------------------- 5.2 recovery of broken lines

CALL_ID_RE = re.compile(r'"call_id"\s*:\s*"((?:[^"\\]|\\.)*)"')


def recover_events(line):
    """5.2 item 1: pull events one by one with raw_decode; after a failure continue at the next `{`."""
    m = re.search(r'"events"\s*:\s*\[', line)
    i = m.end() if m else 0
    dec, out = json.JSONDecoder(), []
    while True:
        j = line.find("{", i)
        if j < 0:
            return out
        try:
            obj, end = dec.raw_decode(line, j)
        except Exception:
            i = j + 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        i = end


def parse_line(line, lineno, notes):
    """Return (call_id, raw_events_or_None, call_meta)."""
    obj = None
    try:
        obj = json.loads(line)
    except Exception:
        obj = None
    if isinstance(obj, dict):
        cid = obj.get("call_id")
        cid = "" if cid is None else str(cid)
        return (cid or "line-%d" % lineno), obj.get("events"), obj
    notes.add("line is not a JSON object, recovering events")
    m = CALL_ID_RE.search(line)
    cid = "line-%d" % lineno
    if m:
        cid = m.group(1)
        try:  # the regex captured the JSON-escaped form
            cid = json.loads('"' + cid + '"')
        except Exception:
            pass
    return cid, recover_events(line), {}


# ---------------------------------------------------------------- 6 / 4d unseen-values summary

def record_seen(seen, meta, evs):
    for e in evs:
        seen["event type"][e["kind"]] += 1
        if e["kind"] in ("tool_call", "tool_result") and e["name"]:
            seen["tool name"][e["name"]] += 1
        if e["kind"] == "tool_result":
            seen["status " + e["name"]][e["status"]] += 1
        elif e["kind"] == "hangup":
            seen["hangup.by"][e["by"]] += 1
        elif e["kind"] == "transfer":
            seen["transfer.status"][e["status"]] += 1
        elif e["kind"] == "route":
            seen["route.target"][e["target"]] += 1
    for key in ("flow_version", "ended_by"):
        if isinstance(meta, dict) and meta.get(key) is not None:
            seen[key][norm(meta[key])] += 1


def print_summary(counts, seen, log):
    total = sum(counts.values())
    log("== label distribution (%d calls) ==" % total)
    for lab in LABELS:
        log("  %-24s %6d" % (lab, counts.get(lab, 0)))
    new = []
    for cat in sorted(seen):
        known = NIGHT1_KNOWN.get(cat)
        if known is None:
            known = set()  # e.g. status of a tool that did not exist on night 1
        for val, n in sorted(seen[cat].items()):
            if val not in known:
                new.append("  %s = %r (%d x)" % (cat, val, n))
    log("== values not seen on night 1 ==")
    for line in new or ["  (none)"]:
        log(line)


# ---------------------------------------------------------------- CLI

def run(in_path, out, log):
    counts, seen = Counter(), defaultdict(Counter)
    # newline="\n": only a real LF ends a row (a lone CR inside a line must not split it; CRLF is stripped)
    with open(in_path, "r", encoding="utf-8-sig", errors="replace", newline="\n") as f:
        writer = csv.writer(out, lineterminator="\n")  # header only once the input is open (fix 4)
        writer.writerow(["call_id", "label"])
        problems = 0
        for lineno, line in enumerate(f, 1):
            line = line.strip().lstrip("﻿")
            if not line:
                continue
            notes = set()
            cid, label = "line-%d" % lineno, FALLBACK
            try:
                cid, raw, meta = parse_line(line, lineno, notes)
                try:
                    label, evs = classify_raw_events(raw, notes)
                    record_seen(seen, meta, evs)
                except ValueError as exc:  # 5.2 item 6: nothing to recover
                    notes.add("fallback %s: %s" % (FALLBACK, exc))
                    label = FALLBACK
            except Exception as exc:  # never drop a call
                notes.add("fallback %s: unexpected %s: %s" % (FALLBACK, type(exc).__name__, exc))
                label = FALLBACK
            if notes:  # 5.2 item 7: every recovery/fallback is logged
                problems += 1
                if problems <= 100:
                    log("[line %d] %s: %s" % (lineno, cid, "; ".join(sorted(notes))))
            writer.writerow([cid, label])
            counts[label] += 1
    if problems > 100:
        log("... %d lines with recovery/fallback notes in total (first 100 shown)" % problems)
    print_summary(counts, seen, log)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Classify voicebot calls (one label per call).")
    ap.add_argument("input", help="transcripts.jsonl")
    ap.add_argument("--out", help="output CSV (default: stdout)")
    args = ap.parse_args(argv)
    for stream, kw in ((sys.stdout, {"newline": ""}), (sys.stderr, {})):
        try:  # AGENTS.md Windows gotchas: cp1252 console, no \r\r\n
            stream.reconfigure(encoding="utf-8", errors="replace", **kw)
        except Exception:
            pass

    def log(msg):
        sys.stderr.write(msg + "\n")

    try:
        # Validate the input before --out is truncated or a header is printed (fix 4).
        with open(args.input, "rb") as probe:
            probe.read(1)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="") as out:
                return run(args.input, out, log)
        return run(args.input, sys.stdout, log)
    except OSError as exc:
        log("error: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
