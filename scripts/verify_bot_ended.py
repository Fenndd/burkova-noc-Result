"""Independent check of calls.csv ended_by == 'bot' against transcripts. stdlib only."""
import csv, json, re, sys, statistics, collections
sys.stdout.reconfigure(encoding="utf-8", newline="")
C = collections.Counter


def norm(s):
    return re.sub(r"\d+", "#", s.strip())


def load():
    meta = {}
    with open("data/calls.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            meta[r["call_id"]] = r
    tr = {}
    with open("data/transcripts.jsonl", encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                d = json.loads(ln)
                tr[d["call_id"]] = d["events"]
    return meta, tr


def hangup(ev):
    h = [e for e in ev if e.get("type") == "hangup"]
    return h[-1] if h else None


GOODBYE = re.compile(r"dovidenia|zbohom", re.I)
STATUS = re.compile(r"poruch", re.I)
TICKET_TXT = re.compile(r"hl[áa]senie|č[íi]slo hl|zaevidoval|zalo[žz]il", re.I)
ADDR_FAIL = re.compile(r"adresu sa mi nepodarilo|nena[šs]la|nerozumel", re.I)
XFER_FAIL = re.compile(r"obsaden", re.I)
API_FAIL = re.compile(r"technick[áa] chyba|nem[ôo][žz]em overi[ťt]|neodpoved", re.I)


def bots(ev):
    return [e for e in ev if e.get("type") == "bot"]


def text_method(ev):
    b = bots(ev)
    if not b:
        return "NO_BOT_TEXT"
    last = b[-1]["text"]
    if GOODBYE.search(last):
        prev = b[-2]["text"] if len(b) > 1 else ""
        if TICKET_TXT.search(prev):
            return "TICKET_CREATED"
        if STATUS.search(prev):
            return "KNOWN_OUTAGE_INFORMED"
        return "GOODBYE_OTHER"
    if XFER_FAIL.search(last):
        return "TRANSFER_FAILED"
    if ADDR_FAIL.search(last):
        return "ADDRESS_NOT_UNDERSTOOD"
    if API_FAIL.search(last):
        return "API_ERROR"
    return "UNMAPPED"


def event_method(ev):
    tr = [e for e in ev if e.get("type") == "transfer"]
    if tr:
        return "TRANSFERRED" if tr[-1].get("status") == "connected" else "TRANSFER_FAILED"
    res = [e for e in ev if e.get("type") == "tool_result"]
    calls = [e for e in ev if e.get("type") == "tool_call"]
    go = [e for e in res if e.get("name") == "get_outage"]
    ct = [e for e in res if e.get("name") == "create_ticket"]
    if any(e.get("name") == "get_outage" for e in calls):
        if not go or go[-1].get("status") != "ok":
            return "API_ERROR"
        oid = (go[-1].get("result") or {}).get("outage_id")
        if oid:
            return "KNOWN_OUTAGE_INFORMED"
        if any(e.get("name") == "create_ticket" for e in calls):
            return "TICKET_CREATED" if ct and ct[-1].get("status") == "ok" else "API_ERROR"
        return "OUTAGE_UNKNOWN_NO_TICKET"
    if any(e.get("name") == "resolve_address" for e in calls):
        return "ADDRESS_NOT_UNDERSTOOD"
    return "NO_TOOL_ACTIVITY"


def main():
    meta, tr = load()
    n = len(meta)
    ec = C(r["ended_by"] for r in meta.values())
    print("== 1. ended_by in calls.csv (n=%d)" % n)
    for k, v in ec.most_common():
        print("  %-10s %6d  %6.2f%%" % (k, v, 100 * v / n))
    print("  transcripts: %d, csv ids missing in transcripts: %d, transcripts not in csv: %d" % (
        len(tr), len(set(meta) - set(tr)), len(set(tr) - set(meta))))

    print("\n== 2. ended_by (csv) vs hangup.by (transcript)")
    mm = C()
    for cid, r in meta.items():
        h = hangup(tr.get(cid, []))
        mm[(r["ended_by"], h["by"] if h else "<no hangup event>")] += 1
    for k, v in sorted(mm.items(), key=lambda x: -x[1]):
        print("  csv=%-8s transcript=%-18s %6d%s" % (k[0], k[1], v, "" if k[0] == k[1] else "   <-- MISMATCH"))
    print("  total mismatches:", sum(v for k, v in mm.items() if k[0] != k[1]))

    botids = [c for c, r in meta.items() if r["ended_by"] == "bot" and c in tr]
    nb = len(botids)
    print("\n== 3a. text method: last bot utterance of bot-ended calls (n=%d)" % nb)
    g = C()
    g2 = C()
    for c in botids:
        b = bots(tr[c])
        g[norm(b[-1]["text"]) if b else "<none>"] += 1
    for k, v in g.most_common():
        print("  %5d  %s" % (v, k))
    print("  -- goodbye groups split by preceding bot utterance (digits->#, ETA phrase collapsed):")
    for c in botids:
        b = bots(tr[c])
        if b and GOODBYE.search(b[-1]["text"]):
            prev = norm(b[-2]["text"]) if len(b) > 1 else "<none>"
            prev = re.sub(r"(mať späť).*", r"\1 <ETA>", prev)
            g2[prev] += 1
    for k, v in g2.most_common():
        print("  %5d  %s" % (v, k))
    ta = {c: text_method(tr[c]) for c in botids}
    print("  text-method outcomes:", dict(C(ta.values())))

    eb = {c: event_method(tr[c]) for c in botids}
    print("\n== 3b. event method outcomes:", dict(C(eb.values())))

    print("\n== 3c. cross-tab rows=text, cols=event")
    cols = sorted(set(eb.values()))
    rows = sorted(set(ta.values()))
    ctab = C((ta[c], eb[c]) for c in botids)
    print("  %-26s" % "" + "".join("%-26s" % x for x in cols))
    for r in rows:
        print("  %-26s" % r + "".join("%-26d" % ctab[(r, x)] for x in cols))
    dis = [c for c in botids if ta[c] != eb[c]]
    print("  disagreements: %d" % len(dis))
    for c in dis[:20]:
        print("   ", c, "text=%s event=%s" % (ta[c], eb[c]))

    print("\n== 4. summary")
    ok = [c for c in botids if ta[c] == "KNOWN_OUTAGE_INFORMED" and eb[c] == "KNOWN_OUTAGE_INFORMED"]
    print("  normal goodbye after known outage status/ETA (both methods): %d = %.2f%% of bot-ended, %.2f%% of all calls" % (
        len(ok), 100 * len(ok) / nb, 100 * len(ok) / n))
    print("    (text only: %d; event only: %d)" % (
        sum(1 for c in botids if ta[c] == "KNOWN_OUTAGE_INFORMED"),
        sum(1 for c in botids if eb[c] == "KNOWN_OUTAGE_INFORMED")))
    fails = C(eb[c] for c in botids if eb[c] not in ("KNOWN_OUTAGE_INFORMED", "TICKET_CREATED", "TRANSFERRED"))
    tf = sum(fails.values())
    print("  bot-ended real failures (event method): %d = %.2f%% of bot-ended, %.2f%% of all calls" % (
        tf, 100 * tf / nb, 100 * tf / n))
    for k, v in fails.most_common():
        print("    %-26s %5d  (%.2f%% of all calls)" % (k, v, 100 * v / n))
    print("  detail of failures by tool status (event method):")
    det = C()
    for c in botids:
        if eb[c] in fails:
            ev = tr[c]
            if eb[c] == "API_ERROR":
                bad = [e for e in ev if e.get("type") == "tool_result" and e.get("name") in ("get_outage", "create_ticket") and e.get("status") != "ok"]
                if bad:
                    det[("API_ERROR", bad[-1]["name"], bad[-1]["status"])] += 1
                else:
                    det[("API_ERROR", "tool_call without result", "")] += 1
            elif eb[c] == "TRANSFER_FAILED":
                det[("TRANSFER_FAILED", [e for e in ev if e["type"] == "transfer"][-1].get("status"), "")] += 1
            else:
                ra = [e.get("status") for e in ev if e.get("type") == "tool_result" and e.get("name") == "resolve_address"]
                det[(eb[c], "resolve_address last=%s" % (ra[-1] if ra else None), "n_calls=%d" % len(ra))] += 1
    for k, v in det.most_common():
        print("    %5d  %s" % (v, k))

    print("\n== 5. did caller hear the status? (goodbye group, both methods agree)")
    gaps = []
    no_status = 0
    no_ok_before = 0
    caller_after = 0
    gb_gaps = []
    for c in ok:
        ev = tr[c]
        hu = hangup(ev)
        st = [e for e in ev if e.get("type") == "bot" and STATUS.search(e["text"])]
        if not st:
            no_status += 1
            continue
        s = st[-1]
        go = [e for e in ev if e.get("type") == "tool_result" and e.get("name") == "get_outage" and e["t"] <= s["t"]]
        if not go or go[-1].get("status") != "ok":
            no_ok_before += 1
        gaps.append(hu["t"] - s["t"])
        if [e for e in ev if e.get("type") == "caller" and e["t"] > s["t"]]:
            caller_after += 1
        gb = [e for e in ev if e.get("type") == "bot" and e["t"] > s["t"]]
        if gb:
            gb_gaps.append(hu["t"] - gb[-1]["t"])
    print("  calls checked: %d; without status utterance: %d; status not preceded by ok get_outage: %d" % (len(ok), no_status, no_ok_before))
    print("  with a caller turn after the status utterance: %d (%.2f%%)" % (caller_after, 100 * caller_after / max(1, len(ok))))
    if gaps:
        print("  gap status utterance -> hangup (s): min=%.1f median=%.1f mean=%.1f max=%.1f" % (min(gaps), statistics.median(gaps), statistics.mean(gaps), max(gaps)))
        print("  gap status -> hangup < 3s: %d, < 5s: %d" % (sum(x < 3 for x in gaps), sum(x < 5 for x in gaps)))
    if gb_gaps:
        print("  gap goodbye utterance -> hangup (s): min=%.1f median=%.1f max=%.1f" % (min(gb_gaps), statistics.median(gb_gaps), max(gb_gaps)))
    dd = 0
    for c in botids:
        h = hangup(tr[c])
        if h and abs(h["t"] - float(meta[c]["duration_s"])) > 2:
            dd += 1
    print("  bot-ended calls where csv duration_s differs from hangup t by >2s: %d" % dd)


if __name__ == "__main__":
    main()
