"""Task 4: should Voltika switch the bot off?  Capacity of night operators vs. demand vs. bot outcomes.

Usage: python scripts/task4_capacity.py      (no args, deterministic, stdlib only)
Reads data/calls.csv, data/transcripts.jsonl, predictions_night1.csv. Hours are LOCAL (UTC+1).
"""
import collections, csv, json, os, sys
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8", newline="")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = timezone(timedelta(hours=1))
OPS_NIGHT, OPS_DAY, MIN_PER_CALL = 3, 12, 4
HELPED = ("KNOWN_OUTAGE_INFORMED", "TICKET_CREATED", "TRANSFERRED")
FAILED = ("API_ERROR", "ADDRESS_NOT_UNDERSTOOD", "TRANSFER_FAILED")
# OMS degradation window, local (from oms_api_metrics.txt buckets 20:40Z..21:25Z)
WIN = (datetime(2026, 11, 15, 21, 40, tzinfo=LOCAL), datetime(2026, 11, 15, 22, 30, tzinfo=LOCAL))


def pct(a, b):
    return f"{a}/{b} ({100 * a / b:.1f} %)" if b else f"{a}/0"


def cap(ops, mins):
    return ops * 60 / mins


def read_csv(p):
    with open(os.path.join(ROOT, p), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


calls = {r["call_id"]: datetime.fromisoformat(r["started_at"].replace("Z", "+00:00")).astimezone(LOCAL)
         for r in read_csv("data/calls.csv")}
label = {r["call_id"]: r["label"] for r in read_csv("predictions_night1.csv")}
conn_t = {}  # call_id -> local time of the connected transfer
with open(os.path.join(ROOT, "data/transcripts.jsonl"), encoding="utf-8") as f:
    for ln in f:
        d = json.loads(ln)
        for e in d["events"]:
            if e.get("type") == "transfer" and e.get("status") == "connected":
                conn_t[d["call_id"]] = calls[d["call_id"]] + timedelta(seconds=e["t"])
                break
N = len(calls)
assert set(calls) == set(label), "calls.csv and predictions differ"
lab_tot = collections.Counter(label.values())
helped = sum(lab_tot[l] for l in HELPED)
failed = sum(lab_tot[l] for l in FAILED)
early = lab_tot["ENDED_EARLY"]
other = N - helped - failed - early

print("== 0. Totals ==")
print(f"calls {N}; labels {dict(sorted(lab_tot.items()))}")
print(f"helped {pct(helped, N)}; failed {pct(failed, N)}; ENDED_EARLY {pct(early, N)}; other {other}")
print(f"connected transfers {len(conn_t)}; TRANSFERRED label {lab_tot['TRANSFERRED']}")

print("\n== 1. Operator capacity (assumption: 100 % utilisation, no breaks, every call same length) ==")
print(f"night: {OPS_NIGHT} x 60/{MIN_PER_CALL} = {cap(OPS_NIGHT, MIN_PER_CALL):.0f} calls/h; "
      f"day: {OPS_DAY} x 60/{MIN_PER_CALL} = {cap(OPS_DAY, MIN_PER_CALL):.0f} calls/h")
print("sensitivity, night capacity by minutes per call:")
for m in (3, 4, 5, 6):
    print(f"  {m} min -> {cap(OPS_NIGHT, m):.0f} calls/h; over 6 h = {6 * cap(OPS_NIGHT, m):.0f}")
CAP = cap(OPS_NIGHT, MIN_PER_CALL)

hours = sorted({t.replace(minute=0, second=0, microsecond=0) for t in calls.values()})
H = {h: collections.Counter() for h in hours}
hconn = collections.Counter()
for c, t in calls.items():
    h = t.replace(minute=0, second=0, microsecond=0)
    H[h]["n"] += 1
    l = label[c]
    H[h]["helped" if l in HELPED else "failed" if l in FAILED else "early" if l == "ENDED_EARLY" else "other"] += 1
    H[h]["toolfail"] += l == "API_ERROR"
for c, t in conn_t.items():
    hconn[t.replace(minute=0, second=0, microsecond=0)] += 1

print(f"\n== 2. Per local hour: demand vs capacity vs bot outcome (capacity {CAP:.0f}/h) ==")
print("hour | demand | cap | demand/cap | unserved w/o bot | helped | failed | early | helped/cap | connected transfers (by transfer time)")
tot_unserved = 0
for h in hours:
    n = H[h]["n"]
    un = max(0, n - CAP)
    tot_unserved += un
    print(f"{h:%H}:00 | {n} | {CAP:.0f} | {n / CAP:.1f}x | {un:.0f} | {H[h]['helped']} | {H[h]['failed']} | "
          f"{H[h]['early']} | {H[h]['helped'] / CAP:.1f}x | {hconn[h]}")
peak_h = max(hours, key=lambda h: H[h]["n"])
print(f"peak hour {peak_h:%H}:00 local: {H[peak_h]['n']} calls = {H[peak_h]['n'] / CAP:.1f}x night capacity")
print(f"hours with demand > capacity: {sum(1 for h in hours if H[h]['n'] > CAP)}/{len(hours)}")
print(f"bot off: operators take at most {sum(min(H[h]['n'], CAP) for h in hours):.0f} calls over {len(hours)} h; "
      f"unserved {tot_unserved:.0f} = {pct(round(tot_unserved), N)}")

q = collections.Counter()
for t in calls.values():
    q[t.replace(minute=t.minute // 15 * 15, second=0)] += 1
pk, pv = max(q.items(), key=lambda kv: kv[1])
print(f"peak 15 min {pk:%H:%M}: {pv} calls = {pv * 4}/h pace; capacity per 15 min = {CAP / 4:.1f}")

print("\n== 3. Scenarios (night total; peak hour) ==")
pk_n = H[peak_h]["n"]
tf = lab_tot["API_ERROR"]
a_tot = sum(min(H[h]["n"], CAP) for h in hours)
print("(a) bot off, operators only (capacity per hour, no abandonment, no queue carry-over):")
print(f"    answered at most {a_tot:.0f}/{N} = {100 * a_tot / N:.1f} %; peak hour {min(pk_n, CAP):.0f}/{pk_n} = {100 * min(pk_n, CAP) / pk_n:.1f} %")
print("(b) bot as on 15.11. (helped = informed + ticket + transferred):")
print(f"    helped {pct(helped, N)}; peak hour {H[peak_h]['helped']}/{pk_n} = {100 * H[peak_h]['helped'] / pk_n:.1f} %")
print(f"    failed {pct(failed, N)}; ENDED_EARLY {pct(early, N)} (left before help; not counted as failure)")
print(f"    helped by bot vs operators-only max: {helped} vs {a_tot:.0f} = {helped / a_tot:.1f}x")
print(f"    resolved by bot without operator: {helped - lab_tot['TRANSFERRED']}; transferred to dispatch: {lab_tot['TRANSFERRED']}")
print(f"(c) UPPER BOUND, assumption not data: the {tf} API_ERROR calls were helped (e.g. got a ticket):")
print(f"    helped {pct(helped + tf, N)}; failed {pct(failed - tf, N)} (address {lab_tot['ADDRESS_NOT_UNDERSTOOD']} + transfer {lab_tot['TRANSFER_FAILED']} unchanged)")
pk_tf = H[peak_h]["toolfail"]
print(f"    peak hour: helped {H[peak_h]['helped'] + pk_tf}/{pk_n} = {100 * (H[peak_h]['helped'] + pk_tf) / pk_n:.1f} %")

print("\n== 4. OMS degradation window 21:40-22:30 local ==")
inw = {c for c, t in calls.items() if WIN[0] <= t < WIN[1]}
wf = sum(label[c] in FAILED for c in inw)
wh = sum(label[c] in HELPED for c in inw)
ae = sum(label[c] == "API_ERROR" for c in inw)
opcap_w = CAP * 50 / 60
print(f"calls in window {len(inw)}; failed {pct(wf, len(inw))} (API_ERROR {ae}); helped {pct(wh, len(inw))}")
print(f"window pace {len(inw) * 60 / 50:.0f}/h vs capacity {CAP:.0f}/h; operators over 50 min: {opcap_w:.0f} calls")
print(f"bot helped {wh} in window vs operators' max {opcap_w:.0f} = {wh / opcap_w:.1f}x")
outside = [c for c in calls if c not in inw]
of = sum(label[c] in FAILED for c in outside)
print(f"outside window failed {pct(of, len(outside))}")
# break-even: bot failure share at which helped == operator max, whole night
print(f"break-even: bot helped count would equal operators-only max ({a_tot:.0f}) if helped share fell to {100 * a_tot / N:.1f} %; actual {100 * helped / N:.1f} %")
# operators needed to cover the peak hour without the bot (one operator = 60/4 = 15 calls/h)
per_op = CAP / 3  # one operator, calls/h
print(f"operators needed for peak {pk_n}/h at 4 min/call: {pk_n / per_op:.0f} (= {pk_n / CAP:.1f}x the 3 night operators)")

print("\n== 5. Sanity check: connected transfers vs what 3 operators take at 4 min/call ==")
print("hour | connected | cap | ratio")
over = 0
for h in hours:
    r = hconn[h]
    over += r > CAP
    print(f"{h:%H}:00 | {r} | {CAP:.0f} | {r / CAP:.1f}x")
print(f"hours with connected > {CAP:.0f}: {over}/{len(hours)}; total connected {len(conn_t)} vs night capacity {CAP * len(hours):.0f}")
print(f"dispatch attempts: connected {len(conn_t)}, TRANSFER_FAILED {lab_tot['TRANSFER_FAILED']}, total {len(conn_t) + lab_tot['TRANSFER_FAILED']}")
print(f"avg minutes/call implied if 3 operators handled the peak connected hour: {OPS_NIGHT * 60 / max(hconn.values()):.1f} min")
