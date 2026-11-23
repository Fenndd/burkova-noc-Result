"""Task 2 (second bullet): how many calls really failed on night 1, and why.

Usage:  python scripts/task2_failures.py [data_dir]        (default: data/)

Prints every number used in docs/task2_failures_by_cause.md. Deterministic,
standard library only. Labels come from classify.py (imported from the repo root);
the script checks them against predictions_night1.csv when that file exists.

Definitions
- "Real failure" = the caller left without the help the line exists for because of
  the bot or a system: labels API_ERROR, ADDRESS_NOT_UNDERSTOOD, TRANSFER_FAILED.
- ENDED_EARLY is NOT counted as a failure; it is split into sub-cases and reported
  separately as borderline.
- Time = calls.csv started_at (UTC) + event t; printed in local time (UTC+1, Nov 15
  is after the DST change). Degradation window is derived from oms_api_metrics.txt.
- Cause of API_ERROR / ENDED_EARLY / address failures is derived from structured
  events only (tool, result status "ok" or not, who hung up, timing), never from
  bot wording. asr_conf is used only as a descriptive correlate for address failures.
"""
import collections
import csv
import json
import os
import re
import statistics
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import classify  # noqa: E402  (the task 1 classifier; single source of labels)

sys.stdout.reconfigure(encoding="utf-8", newline="")

LOCAL = timedelta(hours=1)
FAIL_LABELS = ("API_ERROR", "ADDRESS_NOT_UNDERSTOOD", "TRANSFER_FAILED")
HELP_LABELS = ("KNOWN_OUTAGE_INFORMED", "TICKET_CREATED", "TRANSFERRED")

# Town names are an open vocabulary; these 14 are the ones the bot itself says on night 1
# ("Overim si: <ulica>, <obec>"). Parts of towns come first so "pezinok grinava" is Grinava.
PARTS = collections.OrderedDict([("Grinava", "grinava"), ("Cajla", "cajla"),
                                 ("Kráľová", "kralova"), ("Harmónia", "harmonia")])
TOWNS = collections.OrderedDict([("Pezinok", "pezinok"), ("Modra", "modra"), ("Limbach", "limbach"),
                                 ("Stupava", "stupava"), ("Malacky", "malacky"),
                                 ("Svätý Jur", "svaty jur"), ("Ivanka pri Dunaji", "ivanka"),
                                 ("Senec", "senec"), ("Bernolákovo", "bernolakovo"),
                                 ("Šamorín", "samorin")])

PARENT = {"Grinava": "Pezinok", "Cajla": "Pezinok", "Kráľová": "Modra", "Harmónia": "Modra"}  # bot reads them back as "Pezinok – Cajla"


# ------------------------------------------------------------------ helpers

def pct(a, b, nd=1):
    return "%d/%d (%.*f %%)" % (a, b, nd, 100.0 * a / b) if b else "%d/0" % a


def q5(v):
    """min / p25 / median / p75 / max"""
    v = sorted(v)
    n = len(v)
    return "min %.1f / p25 %.1f / med %.1f / p75 %.1f / max %.1f (n=%d)" % (
        v[0], v[n // 4], statistics.median(v), v[(3 * n) // 4], v[-1], n)


def pctl(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))]


def fold(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def head(title):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / (sxx * syy) ** 0.5


def parse_dt(s):
    return datetime.strptime(s.replace("Z", ""), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ load

DATA_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data")

calls = collections.OrderedDict()
with open(os.path.join(DATA_DIR, "calls.csv"), encoding="utf-8", newline="") as f:
    for r in csv.DictReader(f):
        r["start"] = parse_dt(r["started_at"])
        calls[r["call_id"]] = r

C = []  # list of dicts: id, ev, label, start
with open(os.path.join(DATA_DIR, "transcripts.jsonl"), encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        o = json.loads(line)
        C.append({"id": o["call_id"], "ev": o["events"], "label": classify.classify_call(o),
                  "start": calls[o["call_id"]]["start"], "meta": calls[o["call_id"]]})
N = len(C)
BYID = {c["id"]: c for c in C}


def when(c, t):
    """local datetime of an event"""
    return c["start"] + timedelta(seconds=t) + LOCAL


def lt(c, t=0.0):
    return when(c, t).strftime("%H:%M:%S")


def first(ev, typ, name=None):
    for e in ev:
        if e["type"] == typ and (name is None or e.get("name") == name):
            return e
    return None


def last_hangup(ev):
    h = first(ev, "hangup")
    return h


def show(cid, note=""):
    """Print a call as evidence (local time of call start + compact events)."""
    c = BYID[cid]
    print("  EXAMPLE %s  start %s local  label %s  %s" % (cid, c["start"].__add__(LOCAL).strftime("%H:%M:%S"),
                                                         c["label"], note))
    for e in c["ev"]:
        t = e["type"]
        if t == "bot":
            s = 'bot: "%s"' % e["text"]
        elif t == "caller":
            s = 'caller: "%s" (asr %.2f)' % (e["text"], e.get("asr_conf", -1))
        elif t == "tool_call":
            s = "CALL %s %s" % (e["name"], json.dumps(e["args"], ensure_ascii=False))
        elif t == "tool_result":
            s = "RESULT %s status=%s latency=%sms %s" % (
                e["name"], e["status"], e.get("latency_ms"), json.dumps(e.get("result"), ensure_ascii=False))
        else:
            s = "%s %s" % (t.upper(), {k: v for k, v in e.items() if k not in ("t", "type")})
        print("     t=%5.1f (%s)  %s" % (e["t"], lt(c, e["t"]), s))


# ------------------------------------------------------------------ OMS metrics -> windows

OMS = []  # (bucket_start_utc, requests, p50, p95, err_rate_pct)
with open(os.path.join(DATA_DIR, "oms_api_metrics.txt"), encoding="utf-8") as f:
    for line in f:
        if line.startswith("#") or not line.strip():
            continue
        b, req, p50, p95, er = line.split()
        OMS.append((parse_dt(b.replace("Z", "") + ":00"), int(req), int(p50), int(p95), float(er.rstrip("%"))))
OMS_BY = {b[0]: b for b in OMS}


def oms_phase_of_bucket(b):
    _, req, p50, p95, er = b
    if er >= 20.0:
        return "degraded"
    if p95 > 5000:
        return "tail"
    return None


DEG = [b[0] for b in OMS if oms_phase_of_bucket(b) == "degraded"]
TAIL = [b[0] for b in OMS if oms_phase_of_bucket(b) == "tail"]
DEG0, DEG1 = min(DEG), max(DEG) + timedelta(minutes=5)          # [DEG0, DEG1)
TAIL1 = max(TAIL) + timedelta(minutes=5) if TAIL else DEG1


def phase(dt_utc):
    if dt_utc < DEG0:
        return "before"
    if dt_utc < DEG1:
        return "degraded"
    if dt_utc < TAIL1:
        return "tail"
    return "after"


def fmt_local(dt_utc):
    return (dt_utc + LOCAL).strftime("%H:%M")


PHASES = ("before", "degraded", "tail", "after")
PHASE_NAME = {"before": "before (19:00-%s)" % fmt_local(DEG0),
              "degraded": "degraded (%s-%s)" % (fmt_local(DEG0), fmt_local(DEG1)),
              "tail": "tail (%s-%s)" % (fmt_local(DEG1), fmt_local(TAIL1)),
              "after": "after (%s-01:00)" % fmt_local(TAIL1)}

# ================================================================== 0. sanity
head("0. DATA AND LABELS")
print("calls in transcripts: %d, in calls.csv: %d" % (N, len(calls)))
pred_path = os.path.join(ROOT, "predictions_night1.csv")
if os.path.exists(pred_path):
    with open(pred_path, encoding="utf-8", newline="") as f:
        pred = {r["call_id"]: r["label"] for r in csv.DictReader(f)}
    diff = sum(1 for c in C if pred.get(c["id"]) != c["label"])
    print("labels from classify.py differ from predictions_night1.csv in %d calls" % diff)
cnt = collections.Counter(c["label"] for c in C)
for lab, n in cnt.most_common():
    print("  %-24s %6d  %5.1f %%" % (lab, n, 100.0 * n / N))
ended = collections.Counter(c["meta"]["ended_by"] for c in C)
print("ended_by (calls.csv): %s  -> bot-ended = %s" % (dict(ended), pct(ended["bot"], N)))
print("OMS degradation derived from oms_api_metrics.txt: degraded buckets %s .. %s (UTC) = %s-%s local; tail bucket(s): %s" % (
    DEG[0].strftime("%H:%M"), DEG[-1].strftime("%H:%M"), fmt_local(DEG0), fmt_local(DEG1),
    ", ".join(fmt_local(t) + " local" for t in TAIL)))
print("  OMS in degraded buckets: requests %d, p50 %d-%d ms, p95 %d-%d ms, error rate %.1f-%.1f %%" % (
    sum(OMS_BY[t][1] for t in DEG), min(OMS_BY[t][2] for t in DEG), max(OMS_BY[t][2] for t in DEG),
    min(OMS_BY[t][3] for t in DEG), max(OMS_BY[t][3] for t in DEG),
    min(OMS_BY[t][4] for t in DEG), max(OMS_BY[t][4] for t in DEG)))

real = [c for c in C if c["label"] in FAIL_LABELS]
print("\nREAL FAILURES (API_ERROR + ADDRESS_NOT_UNDERSTOOD + TRANSFER_FAILED) = %s" % pct(len(real), N))

# ================================================================== 1. API_ERROR
head("1. API_ERROR (%d)" % cnt["API_ERROR"])


def api_cause(c):
    ev = c["ev"]
    h = last_hangup(ev)
    hby = h["by"] if h else None
    ct = first(ev, "tool_call", "create_ticket")
    if ct:
        r = [e for e in ev if e["type"] == "tool_result" and e["name"] == "create_ticket"]
        return "create_ticket failed (result %s), bot ended" % (r[-1]["status"] if r else "missing")
    go = [e for e in ev if e["type"] == "tool_call" and e["name"] == "get_outage"]
    if not go:
        return "other (no get_outage/create_ticket)"
    r = [e for e in ev if e["type"] == "tool_result" and e["name"] == "get_outage"]
    if r and r[-1]["status"] != "ok" and h and r[-1]["t"] <= h["t"] and hby != "caller":
        return "get_outage failed (%s), caller still there, bot apologised and hung up" % r[-1]["status"]
    if r and r[-1]["status"] != "ok":
        return "get_outage: caller hung up while waiting, result later failed (%s)" % r[-1]["status"]
    if not r:
        return "get_outage: caller hung up while waiting, no result ever"
    return "other"


api = [c for c in C if c["label"] == "API_ERROR"]
for c in api:
    c["api_cause"] = api_cause(c)
ac = collections.Counter(c["api_cause"] for c in api)
n_go = sum(1 for c in C if first(c["ev"], "tool_call", "get_outage"))
n_ct = sum(1 for c in C if first(c["ev"], "tool_call", "create_ticket"))
print("get_outage calls in the night: %d (calls that called it); create_ticket calls: %d" % (n_go, n_ct))
for k, v in ac.most_common():
    print("  %4d  %s" % (v, k))

K_TO = [k for k in ac if k.startswith("get_outage failed")][0]
K_LATE = [k for k in ac if "later failed" in k][0]
K_NONE = [k for k in ac if "no result ever" in k][0]
K_CT = [k for k in ac if k.startswith("create_ticket")][0]
go_fail = ac[K_TO] + ac[K_LATE] + ac[K_NONE]
print("get_outage did not deliver an answer to the caller: %s of calls that called get_outage" % pct(go_fail, n_go))
print("  (timeouts only: %d; calls with no result: %d)" % (ac[K_TO] + ac[K_LATE], ac[K_NONE]))
n_unknown = sum(1 for c in C if first(c["ev"], "tool_call", "create_ticket"))
print("create_ticket failed: %s of create_ticket calls" % pct(ac[K_CT], n_ct))
print("bot texts at the end of failed-tool calls (what the caller heard):")
tx = collections.Counter()
for c in api:
    if c["api_cause"] in (K_TO, K_CT):
        bots = [e for e in c["ev"] if e["type"] == "bot"]
        tx[(c["api_cause"][:12], bots[-1]["text"])] += 1
for (k, t), v in sorted(tx.items()):
    print("  %3d %s | %s" % (v, k, t))
gaps = [last_hangup(c["ev"])["t"] - [e for e in c["ev"] if e["type"] == "tool_result"][-1]["t"]
        for c in api if c["api_cause"] in (K_TO, K_CT)]
print("seconds from failed result to hangup (bot apologised): %s" % q5(gaps))
print("latency_ms of every failed tool_result: %s" % dict(collections.Counter(
    e["latency_ms"] for c in C for e in c["ev"] if e["type"] == "tool_result" and e["status"] != "ok"
    and e["name"] in ("get_outage", "create_ticket"))))
waits = [last_hangup(c["ev"])["t"] - first(c["ev"], "tool_call", "get_outage")["t"]
         for c in api if c["api_cause"] in (K_LATE, K_NONE)]
print("caller hung up after waiting for get_outage (s): %s" % q5(waits))

# --- time distribution of get_outage calls: transcript vs OMS metrics
print("\n-- get_outage by time of the call (tool_call time, local) vs OMS metrics")
BK = collections.defaultdict(lambda: [0, 0])   # bucket utc -> [calls, failed(no ok answer)]
PH = {p: [0, 0, 0] for p in PHASES}            # calls, failed, later-ok-after-caller-hung-up (ENDED_EARLY sub-case)
ok_lat = {p: [] for p in PHASES}
for c in C:
    ev = c["ev"]
    for i, e in enumerate(ev):
        if e["type"] == "tool_call" and e["name"] == "get_outage":
            t = c["start"] + timedelta(seconds=e["t"])
            b = t.replace(minute=t.minute // 5 * 5, second=0, microsecond=0)
            r = next((x for x in ev[i + 1:] if x["type"] == "tool_result" and x["name"] == "get_outage"), None)
            failed = (r is None) or r["status"] != "ok"
            BK[b][0] += 1
            BK[b][1] += failed
            p = phase(t)
            PH[p][0] += 1
            PH[p][1] += failed
            if r is not None and r["status"] == "ok":
                ok_lat[p].append(r["latency_ms"] / 1000.0)
print("%-24s %9s %9s %9s | OMS requests  OMS err (est.)  OMS p50 ms (range)" % (
    "phase", "get_outage", "no answer", "%"))
for p in PHASES:
    o = [b for b in OMS if phase(b[0]) == p]
    oreq = sum(b[1] for b in o)
    oerr = sum(b[1] * b[4] / 100.0 for b in o)
    print("%-24s %9d %9d %8.1f%% | %9d %10.0f (%.1f%%) %d-%d" % (
        PHASE_NAME[p], PH[p][0], PH[p][1], 100.0 * PH[p][1] / PH[p][0], oreq, oerr, 100.0 * oerr / oreq,
        min(b[2] for b in o), max(b[2] for b in o)))
print("median latency of OK get_outage answers: " + "; ".join(
    "%s %.2f s (n=%d)" % (p, statistics.median(ok_lat[p]), len(ok_lat[p])) for p in PHASES))
dg = PH["degraded"]
tot_f = sum(PH[p][1] for p in PHASES)
print("share of all %d get_outage failures that fall into degraded window: %s; degraded+tail: %s" % (
    tot_f, pct(dg[1], tot_f), pct(dg[1] + PH["tail"][1], tot_f)))

xs, ys = [], []
for b in OMS:
    calls_b, fail_b = BK.get(b[0], [0, 0])
    if calls_b:
        xs.append(b[4])
        ys.append(100.0 * fail_b / calls_b)
print("Pearson r over %d five-minute buckets between OMS error_rate and share of get_outage calls without an answer in the transcripts: %.3f" % (
    len(xs), pearson(xs, ys)))

print("\n5-minute buckets around the window (local time): bucket | transcript get_outage calls, no answer, % | OMS requests, p95 ms, err %")
for b in OMS:
    loc = b[0] + LOCAL
    if "21:15" <= loc.strftime("%H:%M") <= "22:50":
        cb, fb = BK.get(b[0], [0, 0])
        print("  %s  %4d %4d %5.1f%% | %4d %5d %5.1f%%" % (loc.strftime("%H:%M"), cb, fb, 100.0 * fb / cb if cb else 0, b[1], b[3], b[4]))

print("\n-- API_ERROR causes by phase (time of the failing tool call)")
print("%-24s %s" % ("phase", " | ".join(k[:34] for k in (K_TO, K_LATE, K_NONE, K_CT))))
for p in PHASES:
    row = []
    for k in (K_TO, K_LATE, K_NONE, K_CT):
        n = 0
        for c in api:
            if c["api_cause"] == k:
                ev = c["ev"]
                tc = [e for e in ev if e["type"] == "tool_call" and e["name"] in ("get_outage", "create_ticket")][-1]
                if phase(c["start"] + timedelta(seconds=tc["t"])) == p:
                    n += 1
        row.append(n)
    print("%-24s %s" % (PHASE_NAME[p], "  ".join("%6d" % x for x in row)))

print("\n-- create_ticket (counted on the time of the create_ticket call)")
CT = {p: [0, 0] for p in PHASES}
for c in C:
    for i, e in enumerate(c["ev"]):
        if e["type"] == "tool_call" and e["name"] == "create_ticket":
            r = next((x for x in c["ev"][i + 1:] if x["type"] == "tool_result" and x["name"] == "create_ticket"), None)
            p = phase(c["start"] + timedelta(seconds=e["t"]))
            CT[p][0] += 1
            CT[p][1] += (r is None or r["status"] != "ok")
for p in PHASES:
    print("  %-24s create_ticket calls %4d, failed %3d  (%.1f %%)" % (PHASE_NAME[p], CT[p][0], CT[p][1],
                                                                       100.0 * CT[p][1] / CT[p][0]))

# examples
print("\n-- evidence")
ex_to_in = next(c for c in api if c["api_cause"] == K_TO and phase(c["start"] + timedelta(seconds=first(c["ev"], "tool_call", "get_outage")["t"])) == "degraded")
ex_to_out = next(c for c in api if c["api_cause"] == K_TO and phase(c["start"] + timedelta(seconds=first(c["ev"], "tool_call", "get_outage")["t"])) == "before")
ex_late = next(c for c in api if c["api_cause"] == K_LATE)
ex_none = next(c for c in api if c["api_cause"] == K_NONE)
ex_ct_in = next(c for c in api if c["api_cause"] == K_CT and phase(c["start"] + timedelta(seconds=first(c["ev"], "tool_call", "create_ticket")["t"])) == "degraded")
ex_ct_out = next(c for c in api if c["api_cause"] == K_CT and phase(c["start"] + timedelta(seconds=first(c["ev"], "tool_call", "create_ticket")["t"])) != "degraded")
show(ex_to_in["id"], "[get_outage timeout, inside degradation window]")
show(ex_to_out["id"], "[get_outage timeout, before window = background]")
show(ex_late["id"], "[caller hung up waiting, later timeout]")
show(ex_none["id"], "[caller hung up waiting, no result]")
show(ex_ct_in["id"], "[create_ticket timeout, inside window]")
show(ex_ct_out["id"], "[create_ticket timeout, outside window]")

# ================================================================== 2. ADDRESS_NOT_UNDERSTOOD


def attempts(c):
    """resolve_address attempts: asr of the caller utterance just before the call, status, text"""
    res, last = [], None
    ev = c["ev"]
    for i, e in enumerate(ev):
        if e["type"] == "caller":
            last = e
        elif e["type"] == "tool_call" and e["name"] == "resolve_address":
            r = next((x for x in ev[i + 1:] if x["type"] == "tool_result" and x["name"] == "resolve_address"), None)
            b = next((x for x in ev[i + 1:] if x["type"] == "bot"), None)
            res.append({"asr": last["asr_conf"] if last else None, "status": r["status"] if r else None,
                        "text": e["args"].get("text", ""), "bot": b["text"] if b else ""})
    return res


def town_word(text):
    f = fold(text)
    for k, v in PARTS.items():
        if v in f:
            return k
    for k, v in TOWNS.items():
        if v in f:
            return k
    return None


def call_town(atts):
    """a call is a town-part call if ANY attempt mentions a part; else the first town mentioned"""
    ws = [town_word(a["text"]) for a in atts]
    for w in ws:
        if w in PARTS:
            return w
    for w in ws:
        if w:
            return w
    return "?"


head("2. ADDRESS_NOT_UNDERSTOOD (%d)" % cnt["ADDRESS_NOT_UNDERSTOOD"])
for c in C:
    c["att"] = attempts(c)
with_res = [c for c in C if c["att"]]
anu = [c for c in C if c["label"] == "ADDRESS_NOT_UNDERSTOOD"]
print("calls that reached resolve_address: %d; of them ADDRESS_NOT_UNDERSTOOD: %s" % (len(with_res), pct(len(anu), len(with_res))))
print("number of resolve attempts in the %d failed calls: %s; hangup by: %s" % (
    len(anu), dict(collections.Counter(len(c["att"]) for c in anu)),
    dict(collections.Counter(last_hangup(c["ev"])["by"] for c in anu))))


def anu_group(c):
    a = c["att"]
    if all(x["status"] == "ok" for x in a):
        return "C resolver returned an address (ok) that the caller rejected"
    if max(x["asr"] for x in a) >= 0.8:
        return "B at least one attempt well recognised (asr >= 0.8) but not found"
    return "A every attempt asr < 0.8, not found"


for c in anu:
    c["anu_group"] = anu_group(c)
ag = collections.Counter(c["anu_group"] for c in anu)
for k in sorted(ag):
    print("  %4d  %s" % (ag[k], k))
GA, GB, GC = sorted(ag)

print("\n-- asr_conf and resolver status over ALL %d resolve attempts of the night" % sum(len(c["att"]) for c in C))
allatt = [(a, c) for c in C for a in c["att"]]
st_n = collections.Counter(a["status"] for a, _ in allatt)
print("  status counts: %s" % dict(st_n))
for s in sorted(st_n):
    v = [a["asr"] for a, _ in allatt if a["status"] == s]
    print("  status %-9s mean asr %.2f, share asr < 0.6: %s" % (s, sum(v) / len(v), pct(sum(1 for x in v if x < 0.6), len(v))))
print("  attempt failure rate (status != ok) by asr band:")
for lo, hi_ in ((0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
    sel = [a for a, _ in allatt if lo <= a["asr"] < hi_]
    print("    asr %.1f-%.1f: %s" % (lo, min(hi_, 1.0), pct(sum(1 for a in sel if a["status"] != "ok"), len(sel))))
print("  caveat: ok attempts that the caller then rejected (group C) are counted as ok here.")

print("\n-- town parts (Grinava, Cajla, Kralova, Harmonia) vs other towns; call town = any attempt text mentions it")
TW = collections.OrderedDict((k, {"calls": 0, "anu": 0, "att": 0, "attf": 0, "hi": 0, "hif": 0}) for k in list(PARTS) + list(TOWNS))
for c in with_res:
    t = call_town(c["att"])
    if t == "?":
        continue
    TW[t]["calls"] += 1
    TW[t]["anu"] += c["label"] == "ADDRESS_NOT_UNDERSTOOD"
    for a in c["att"]:
        TW[t]["att"] += 1
        TW[t]["attf"] += a["status"] != "ok"
        if a["asr"] >= 0.8:
            TW[t]["hi"] += 1
            TW[t]["hif"] += a["status"] != "ok"
print("  %-18s %6s %12s %16s %22s" % ("town", "calls", "ANU calls", "failed attempts", "failed attempts asr>=0.8"))
for k, v in TW.items():
    print("  %-18s %6d %12s %16s %22s" % (k, v["calls"], pct(v["anu"], v["calls"]), pct(v["attf"], v["att"]), pct(v["hif"], v["hi"])))


def agg(keys):
    return {f: sum(TW[k][f] for k in keys) for f in ("calls", "anu", "att", "attf", "hi", "hif")}


P, O = agg(PARTS), agg(TOWNS)
for nm, v in (("TOWN PARTS (4)", P), ("OTHER TOWNS (10)", O)):
    print("  %-18s %6d %12s %16s %22s" % (nm, v["calls"], pct(v["anu"], v["calls"]), pct(v["attf"], v["att"]), pct(v["hif"], v["hi"])))
unk = [c for c in with_res if call_town(c["att"]) == "?"]
print("  calls with no recognised town word in any attempt: %d" % len(unk))
tot_att = sum(len(c["att"]) for c in with_res)
tot_attf = sum(1 for a, _ in allatt if a["status"] != "ok")
print("  average failed attempts over all attempts: %s" % pct(tot_attf, tot_att))
print("  failed attempts whose text contains NO recognisable town word (garbled): %s" % pct(
    sum(1 for a, _ in allatt if a["status"] != "ok" and town_word(a["text"]) is None), tot_attf))
print("  ANU calls that mention a town part: %s; town-part calls are %s of calls that reached the resolver" % (
    pct(P["anu"], len(anu)), pct(P["calls"], len(with_res))))
for g in (GA, GB, GC):
    sel = [c for c in anu if c["anu_group"] == g]
    print("  group %s: town-part calls %s" % (g[0], pct(sum(1 for c in sel if call_town(c["att"]) in PARTS), len(sel))))
hi_f = [(a, c) for a, c in allatt if a["asr"] >= 0.8 and a["status"] != "ok"]
print("  failed attempts with asr >= 0.8: %d, of them in a call mentioning a town part: %s" % (
    len(hi_f), pct(sum(1 for a, c in hi_f if call_town(c["att"]) in PARTS), len(hi_f))))

print("\n-- group C (resolver returned something the caller rejected)")
gc_calls = [c for c in anu if c["anu_group"] == GC]
mism = 0
asrs = []
same_id = 0
for c in gc_calls:
    for a in c["att"]:
        asrs.append(a["asr"])
    ids = [e["result"]["address_id"] for e in c["ev"] if e["type"] == "tool_result" and e["name"] == "resolve_address"]
    same_id += len(set(ids)) == 1
    caller_town = call_town(c["att"])
    m = re.search(r", (.*?)\. Je to", c["att"][0]["bot"])
    ret = m.group(1) if m else "?"
    if caller_town != "?" and ret.split(" – ")[0] != caller_town.split(" – ")[0]:
        mism += 1
print("  calls %d; same address_id returned on both attempts: %s; returned town differs from the town the caller said: %s" % (
    len(gc_calls), pct(same_id, len(gc_calls)), pct(mism, len(gc_calls))))
print("  caller's asr on those attempts: %s" % q5(asrs))
rej = collections.Counter(next(e["text"] for e in c["ev"] if e["type"] == "caller" and e is not None and
                               c["ev"].index(e) > 3 and ("nie" in e["text"])) for c in gc_calls if any(
    e["type"] == "caller" and "nie" in e["text"] for e in c["ev"][3:]))
print("  caller's rejection phrases (first one in the call), top: %s" % rej.most_common(4))

print("\n-- evidence")
for g in (GA, GB, GC):
    sel = [c for c in anu if c["anu_group"] == g]
    if g == GA:
        sel = [c for c in sel if call_town(c["att"]) not in PARTS] or sel
    show(sel[0]["id"], "[group %s]" % g[0])
sel = [c for c in anu if c["anu_group"] == GB and call_town(c["att"]) in PARTS]
show(sel[0]["id"], "[group B, town part]")
sel = [c for c in anu if c["anu_group"] == GB and call_town(c["att"]) not in PARTS]
show(sel[0]["id"], "[group B, ordinary town]")

# ================================================================== 3. TRANSFER_FAILED
head("3. TRANSFER_FAILED (%d)" % cnt["TRANSFER_FAILED"])
trs = []
for c in C:
    ev = c["ev"]
    T = [e for e in ev if e["type"] == "transfer"]
    if T:
        t = T[-1]
        pre = [e for e in ev[:ev.index(t)] if e["type"] == "bot"][-1]
        trs.append({"c": c, "status": t["status"], "has_addr": first(ev, "tool_call", "resolve_address") is not None,
                    "wait": t["t"] - pre["t"], "ticket": first(ev, "tool_call", "create_ticket") is not None,
                    "after": tuple(e["text"] for e in ev[ev.index(t) + 1:] if e["type"] == "bot"),
                    "before": pre["text"], "hour": when(c, 0).strftime("%H")})
print("transfer attempts (calls with a transfer event): %d (%.1f %% of all calls)" % (len(trs), 100.0 * len(trs) / N))
for s in sorted(set(x["status"] for x in trs)):
    sel = [x for x in trs if x["status"] == s]
    print("  status %-11s %4d   seconds from bot's 'connecting you' to transfer result: %s" % (s, len(sel), q5([x["wait"] for x in sel])))
fail_t = [x for x in trs if x["status"] != "connected"]
print("failed transfers: %s of transfer attempts" % pct(len(fail_t), len(trs)))
print("what the bot said before the transfer: %s" % dict(collections.Counter(x["before"] for x in trs)))
print("what the bot said after a failed transfer: %s" % dict(collections.Counter(x["after"] for x in fail_t)))
print("failed transfers with a ticket created: %d" % sum(x["ticket"] for x in fail_t))
print("\n  with / without a resolve_address attempt (address asked before the transfer):")
for ha in (True, False):
    sel = [x for x in trs if x["has_addr"] == ha]
    f = [x for x in sel if x["status"] != "connected"]
    print("    %-22s transfers %4d, failed %s (queue_full %d, timeout %d)" % (
        "address stage reached" if ha else "no address asked", len(sel), pct(len(f), len(sel)),
        sum(x["status"] == "queue_full" for x in f), sum(x["status"] == "timeout" for x in f)))
print("\n  by local hour of call start: transfers, failed, failed %")
for h in sorted(set(x["hour"] for x in trs)):
    sel = [x for x in trs if x["hour"] == h]
    f = [x for x in sel if x["status"] != "connected"]
    print("    %s:00  %4d %4d  %.1f %%   (queue_full %d, timeout %d)" % (
        h, len(sel), len(f), 100.0 * len(f) / len(sel), sum(x["status"] == "queue_full" for x in f), sum(x["status"] == "timeout" for x in f)))
iv = []
for x in trs:
    c = x["c"]
    T = [e for e in c["ev"] if e["type"] == "transfer"][-1]
    pre = [e for e in c["ev"][:c["ev"].index(T)] if e["type"] == "bot"][-1]
    iv.append((c["start"] + timedelta(seconds=pre["t"]), c["start"] + timedelta(seconds=T["t"]), x["status"]))


def conc(i):
    end = iv[i][1]
    return sum(1 for j, o in enumerate(iv) if j != i and o[0] <= end < o[1])


qf = [conc(i) for i in range(len(iv)) if iv[i][2] == "queue_full"]
cn = [conc(i) for i in range(len(iv)) if iv[i][2] == "connected"]
print()
print("  other bot transfers still waiting at the moment of the result (proxy for queue length, bot calls only):")
print("    at queue_full: min %d / median %.0f / max %d (n=%d);  at connected: min %d / median %.0f / max %d (n=%d)" % (
    min(qf), statistics.median(qf), max(qf), len(qf), min(cn), statistics.median(cn), max(cn), len(cn)))
print("    transfers with >= 10 other bot transfers waiting at that moment: %d of %d" % (sum(1 for i in range(len(iv)) if conc(i) >= 10), len(iv)))
print("\n-- evidence")
show(next(x["c"]["id"] for x in trs if x["status"] == "queue_full" and not x["has_addr"]), "[queue_full, no address]")
show(next(x["c"]["id"] for x in trs if x["status"] == "timeout" and x["has_addr"]), "[timeout after address + outage lookup]")
show(next(x["c"]["id"] for x in trs if x["status"] == "queue_full" and x["has_addr"]), "[queue_full after address]")

# ================================================================== 4. ENDED_EARLY (borderline)
head("4. ENDED_EARLY (%d) - borderline, not counted as failure" % cnt["ENDED_EARLY"])
firstutt = [c["ev"][1]["t"] for c in C if len(c["ev"]) > 1 and c["ev"][1]["type"] == "caller"]
react = []
for c in C:
    ev = c["ev"]
    if len(ev) >= 2 and ev[1]["type"] == "caller":
        nxt = next((x for x in ev[2:] if x["type"] in ("bot", "tool_call", "transfer", "route")), None)
        if nxt:
            react.append(nxt["t"] - ev[1]["t"])
print("baseline: time of caller's first utterance in calls that have one: %s" % q5(firstutt))
print("baseline: seconds from caller's FIRST utterance to the bot's next action (reply/tool call): %s; p90 %.1f" % (q5(react), pctl(react, 0.9)))
ee = [c for c in C if c["label"] == "ENDED_EARLY"]
E1, E2, E3, E4 = [], [], [], []
for c in ee:
    types = [e["type"] for e in c["ev"]]
    if types == ["bot", "hangup"]:
        E1.append(c)
    elif types == ["bot", "caller", "hangup"]:
        E2.append(c)
    elif first(c["ev"], "tool_call", "get_outage") and first(c["ev"], "tool_result", "get_outage") and \
            first(c["ev"], "tool_result", "get_outage")["status"] == "ok" and \
            first(c["ev"], "hangup")["t"] < first(c["ev"], "tool_result", "get_outage")["t"]:
        E3.append(c)
    else:
        E4.append(c)
print("sub-cases: E1 hung up on the greeting (no utterance) %d; E2 one utterance, bot never responded %d; "
      "E3 hung up while get_outage was running, answer ok arrived later %d; other %d" % (len(E1), len(E2), len(E3), len(E4)))
h1 = [last_hangup(c["ev"])["t"] for c in E1]
print("E1 hangup time after call start (s): %s" % q5(h1))
print("   hung up earlier than the earliest first utterance of any normal call (%.1f s): %s" % (min(firstutt), pct(sum(1 for t in h1 if t < min(firstutt)), len(h1))))
txt2 = collections.Counter(c["ev"][1]["text"] for c in E2)
print("E2 what the caller said: %s" % dict(txt2))
print("   all calls whose first utterance is one of these phrases: %s" % pct(
    sum(1 for c in C if len(c["ev"]) > 1 and c["ev"][1]["type"] == "caller" and c["ev"][1]["text"] in txt2 and c["label"] == "ENDED_EARLY"),
    sum(1 for c in C if len(c["ev"]) > 1 and c["ev"][1]["type"] == "caller" and c["ev"][1]["text"] in txt2)))
g2 = [last_hangup(c["ev"])["t"] - c["ev"][1]["t"] for c in E2]
print("   seconds from utterance to hangup, no bot reaction: %s" % q5(g2))
print("   asr_conf of the utterance: %s" % q5([c["ev"][1]["asr_conf"] for c in E2]))
oth = [c for c in C if c["label"] != "ENDED_EARLY" and len(c["ev"]) > 1 and c["ev"][1]["type"] == "caller"]
print("   for comparison, first utterances of all other calls: asr %s; with asr < 0.7: %d" % (
    q5([c["ev"][1]["asr_conf"] for c in oth]), sum(1 for c in oth if c["ev"][1]["asr_conf"] < 0.7)))
low = [c for c in oth if c["ev"][1]["asr_conf"] < 0.7 and c["label"] not in ("TRANSFERRED", "TRANSFER_FAILED", "OUT_OF_SCOPE")]
print("   of those (excluding transfers/route), the bot tried the resolver in: %s" % pct(sum(1 for c in low if c["att"]), len(low)))
p50r, p90r = statistics.median(react), pctl(react, 0.9)
print("   hung up after the normal median reaction (%.1f s): %s; after the normal p90 (%.1f s): %s" % (
    p50r, pct(sum(1 for x in g2 if x > p50r), len(g2)), p90r, pct(sum(1 for x in g2 if x > p90r), len(g2))))
print("   share of calls by local hour (E1+E2 per calls started in that hour):")
hrs = collections.Counter(when(c, 0).strftime("%H") for c in C)
for h in sorted(hrs):
    n12 = sum(1 for c in E1 + E2 if when(c, 0).strftime("%H") == h)
    print("      %s:00  %4d of %4d  (%.1f %%)" % (h, n12, hrs[h], 100.0 * n12 / hrs[h]))
w3 = [last_hangup(c["ev"])["t"] - first(c["ev"], "tool_call", "get_outage")["t"] for c in E3]
l3 = [first(c["ev"], "tool_result", "get_outage")["latency_ms"] / 1000.0 for c in E3]
late = [first(c["ev"], "tool_result", "get_outage")["t"] - last_hangup(c["ev"])["t"] for c in E3]
print("E3 how long the caller waited in silence before hanging up (s): %s" % q5(w3))
print("   how long the lookup actually took (latency_ms, s): %s" % q5(l3))
print("   answer came this many seconds AFTER the hangup: %s" % q5(late))
print("   get_outage ok answers overall: median latency %.2f s; outside the degradation window %.2f s" % (
    statistics.median(sum((ok_lat[p] for p in PHASES), [])), statistics.median(ok_lat["before"] + ok_lat["after"])))
by_ph = collections.Counter(phase(c["start"] + timedelta(seconds=first(c["ev"], "tool_call", "get_outage")["t"])) for c in E3)
print("   E3 by phase: %s" % {p: by_ph[p] for p in PHASES})
print("   E3 as share of get_outage calls in the phase: %s" % "; ".join("%s %s" % (p, pct(by_ph[p], PH[p][0])) for p in PHASES))
# answered ok: how often the caller left before the answer, by how long the OMS took
print("   OK answers by lookup time: caller left before the answer / all OK answers")
for lo, hi_ in ((0, 1), (1, 2), (2, 3), (3, 5), (5, 99)):
    n = left = 0
    for c in C:
        g = first(c["ev"], "tool_call", "get_outage")
        r = first(c["ev"], "tool_result", "get_outage")
        h = first(c["ev"], "hangup")
        if g and r and r["status"] == "ok" and lo <= r["latency_ms"] / 1000.0 < hi_:
            n += 1
            left += (h is not None and h["by"] == "caller" and h["t"] < r["t"])
    print("      %d-%s s: %s" % (lo, hi_ if hi_ < 99 else "inf", pct(left, n)))
print("   bot speech between the get_outage call and the caller's hangup (E3): %d calls with any bot event in between" % sum(
    1 for c in E3 if any(e["type"] == "bot" and first(c["ev"], "tool_call", "get_outage")["t"] < e["t"] < last_hangup(c["ev"])["t"] for e in c["ev"])))
print("\n-- evidence")
show(E1[0]["id"], "[E1]")
show(E2[0]["id"], "[E2]")
inw = next(c for c in E3 if phase(c["start"] + timedelta(seconds=first(c["ev"], "tool_call", "get_outage")["t"])) == "degraded")
show(E3[0]["id"], "[E3]")
show(inw["id"], "[E3 inside window]")

# ================================================================== 5. quality problems in 'successful' calls
head("5. QUALITY PROBLEMS INSIDE SUCCESSFUL CALLS (not failures)")
known = [c for c in C if c["label"] == "KNOWN_OUTAGE_INFORMED"]
past, past_min = [], []
for c in known:
    r = [e for e in c["ev"] if e["type"] == "tool_result" and e["name"] == "get_outage" and e["status"] == "ok"
         and isinstance(e.get("result"), dict) and e["result"].get("outage_id")][-1]
    eta = r["result"].get("eta")
    if not eta:
        continue
    now = c["start"] + timedelta(seconds=r["t"])
    d = (now - datetime.fromisoformat(eta)).total_seconds() / 60.0
    if d > 0:
        past.append((c, eta, d))
        past_min.append(d)
print("5a. ETA already in the past when the bot told it: %s of KNOWN_OUTAGE_INFORMED" % pct(len(past), len(known)))
print("    minutes in the past: min %.1f / median %.1f / max %.1f; more than 15 min: %s; more than 60 min: %s" % (
    min(past_min), statistics.median(past_min), max(past_min), pct(sum(1 for x in past_min if x > 15), len(known)),
    pct(sum(1 for x in past_min if x > 60), len(known))))
print("    those calls ended by: %s" % dict(collections.Counter(last_hangup(c["ev"])["by"] for c, _, _ in past)))
exl = [x for x in past if x[2] > 30 and len(x[0]["att"]) == 1][0]
show(exl[0]["id"], "[ETA in the past by %.0f min; eta=%s]" % (exl[2], exl[1]))

tk = []
for c in C:
    ev = c["ev"]
    for i, e in enumerate(ev):
        if e["type"] == "tool_call" and e["name"] == "create_ticket":
            prevbot = [x for x in ev[:i] if x["type"] == "bot"][-1]["text"]
            callers_between = [x for x in ev[:i] if x["type"] == "caller" and x["t"] > [y for y in ev[:i] if y["type"] == "bot"][-1]["t"]]
            tk.append((c, e["args"].get("description") == prevbot, bool(callers_between)))
print("\n5b. ticket description == the bot's own previous sentence: %s of create_ticket calls" % pct(sum(1 for x in tk if x[1]), len(tk)))
print("    the caller said something after that prompt (so a real description existed in the call): %s" % pct(sum(1 for x in tk if x[2]), len(tk)))
print("    tickets with status ok (TICKET_CREATED): %d" % cnt["TICKET_CREATED"])
tcx = next(x for x in tk if x[0]["label"] == "TICKET_CREATED")
show(tcx[0]["id"], "[ticket description = bot sentence]")

print("\n5c. get_outage answer inconsistency: see docs/outage_consistency_evidence.md; reproduce with python scripts/check_outage_consistency.py")

# 5d. control: does the resolver silently return a wrong town that the caller then ACCEPTS?
mis_att, tot_att_t = collections.Counter(), collections.Counter()
for c in C:
    for a in c["att"]:
        m = re.match(r"Overím si: .*, (.*?)\. Je to", a["bot"])
        said = PARENT.get(call_town([a]), call_town([a]))
        if a["status"] == "ok" and m and said != "?":
            tot_att_t[c["label"]] += 1
            if m.group(1).split(" – ")[0] != said.split(" – ")[0]:
                mis_att[c["label"]] += 1
print("\n5d. control: resolver read back a town different from the one the caller said (by label of the call): %s of %s" % (
    dict(mis_att), dict(tot_att_t)))
print("    mismatches outside ADDRESS_NOT_UNDERSTOOD: %d" % sum(v for k, v in mis_att.items() if k != "ADDRESS_NOT_UNDERSTOOD"))

# ================================================================== 6. repeat callers
head("6. DO THE SAME CALLERS GET HELP ON A LATER CALL (caller_hash)")
byc = collections.defaultdict(list)
for c in C:
    byc[c["meta"]["caller_hash"]].append(c)
fl = collections.Counter()
rec = collections.Counter()
for h, L in byc.items():
    L.sort(key=lambda c: (c["start"], c["id"]))
    for i, c in enumerate(L):
        if c["label"] in FAIL_LABELS:
            fl[c["label"]] += 1
            if any(x["label"] in HELP_LABELS for x in L[i + 1:]):
                rec[c["label"]] += 1
for k in FAIL_LABELS:
    print("  %-24s later call by the same caller_hash with KNOWN/TICKET/TRANSFERRED: %s" % (k, pct(rec[k], fl[k])))
print("  all real failures: %s" % pct(sum(rec.values()), sum(fl.values())))
fcallers = set(c["meta"]["caller_hash"] for c in real)
print("  unique caller_hash among real-failure calls: %d (of %d failed calls)" % (len(fcallers), len(real)))
rec_cal = 0
for h in fcallers:
    L = byc[h]
    ff = next(i for i, c in enumerate(L) if c["label"] in FAIL_LABELS)
    rec_cal += any(x["label"] in HELP_LABELS for x in L[ff + 1:])
print("  of them callers who got KNOWN/TICKET/TRANSFERRED on a later call: %s; never helped after the first failure: %d" % (
    pct(rec_cal, len(fcallers)), len(fcallers) - rec_cal))

# ================================================================== 7. by hour
head("7. REAL FAILURES BY LOCAL HOUR OF CALL START")
print("hour   calls   API_ERROR   ADDRESS   TRANSFER_F   real %   ENDED_EARLY")
for h in sorted(hrs):
    sel = [c for c in C if when(c, 0).strftime("%H") == h]
    k = collections.Counter(c["label"] for c in sel)
    rf = sum(k[x] for x in FAIL_LABELS)
    print("%s:00 %6d %10d %9d %11d %6.1f%% %10d" % (h, len(sel), k["API_ERROR"], k["ADDRESS_NOT_UNDERSTOOD"], k["TRANSFER_FAILED"],
                                                   100.0 * rf / len(sel), k["ENDED_EARLY"]))

# ================================================================== 8. totals
head("8. TOTALS: CAUSE -> CALLS -> % OF ALL CALLS -> % OF REAL FAILURES")
rows = [
    ("get_outage did not answer, caller still there, bot apologised and hung up", ac[K_TO]),
    ("get_outage: caller hung up while waiting, result later timeout", ac[K_LATE]),
    ("get_outage: caller hung up while waiting, no result", ac[K_NONE]),
    ("create_ticket timeout (unknown outage, no ticket)", ac[K_CT]),
    ("address: every attempt asr < 0.8", ag[GA]),
    ("address: a well recognised attempt (asr >= 0.8) still not found", ag[GB]),
    ("address: resolver returned an address the caller rejected", ag[GC]),
    ("transfer: queue_full", sum(1 for x in fail_t if x["status"] == "queue_full")),
    ("transfer: timeout", sum(1 for x in fail_t if x["status"] == "timeout")),
]
other_fail = len(real) - sum(r[1] for r in rows)
print("sum of the rows: %d; real failures: %d; unexplained remainder: %d" % (sum(r[1] for r in rows), len(real), other_fail))
for nm, n in sorted(rows, key=lambda r: -r[1]):
    print("  %-78s %5d  %5.2f %% of all  %5.1f %% of failures" % (nm, n, 100.0 * n / N, 100.0 * n / len(real)))
print("  %-78s %5d  %5.2f %% of all  %5.1f %% of failures" % ("TOTAL real failures", len(real), 100.0 * len(real) / N, 100.0))
print("\nroll-up by tool/stage:")
for nm, n in (("get_outage (OMS lookup)", go_fail), ("address (resolve_address)", len(anu)), ("transfer to dispatch", len(fail_t)),
              ("create_ticket", ac[K_CT])):
    print("  %-28s %5d  %5.2f %% of all  %5.1f %% of failures" % (nm, n, 100.0 * n / N, 100.0 * n / len(real)))

print("\nborderline ENDED_EARLY sub-cases and the alternative totals:")
print("  real failures only:                                     %s" % pct(len(real), N))
print("  + E3 (hung up while an ok answer was on the way):       %s" % pct(len(real) + len(E3), N))
print("  + E3 + E2 (said 'halo' etc., bot never responded):      %s" % pct(len(real) + len(E3) + len(E2), N))
print("  + all ENDED_EARLY incl. E1 (upper bound, 'no help'):    %s" % pct(len(real) + len(ee), N))
print("  ENDED_EARLY sub-cases: E1 %d, E2 %d, E3 %d, other %d" % (len(E1), len(E2), len(E3), len(E4)))
print("  for scale: bot-ended calls in calls.csv = %s; of them real failures %s" % (
    pct(ended["bot"], N), pct(sum(1 for c in real if c["meta"]["ended_by"] == "bot"), ended["bot"])))
print("  real failures where the caller hung up: %d (those are the %d + %d 'caller hung up while waiting' API_ERRORs)" % (
    sum(1 for c in real if c["meta"]["ended_by"] == "caller"), ac[K_LATE], ac[K_NONE]))
