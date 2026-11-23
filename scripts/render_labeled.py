#!/usr/bin/env python3
"""Render data/labeled_sample.jsonl into a human-readable markdown file."""
import argparse
import json
from collections import Counter


def dumps(x):
    return json.dumps(x, ensure_ascii=False, separators=(", ", ": "))


def fmt_event(e):
    if not isinstance(e, dict):
        return f"{'':6}  ?       {dumps(e)}"
    t = e.get("t")
    ts = f"{t:6.1f}" if isinstance(t, (int, float)) else f"{'':6}"
    typ = e.get("type")
    rest = {k: v for k, v in e.items() if k not in ("t", "type")}

    def line(tag, body, stamp=ts):
        return f"{stamp}  {tag:<9}{body}".rstrip()

    if typ == "bot":
        return line("BOT", str(e.get("text", "—")))
    if typ == "caller":
        conf = e.get("asr_conf")
        extra = f"   (asr {conf:.2f})" if isinstance(conf, (int, float)) else ""
        return line("CALLER", f"{e.get('text', '—')}{extra}")
    if typ == "tool_call":
        return line("CALL", f"{e.get('name', '?')} {dumps(e.get('args', {}))}")
    if typ == "tool_result":
        lat = e.get("latency_ms")
        lat_s = f"{lat}ms" if lat is not None else "—"
        res = dumps(e["result"]) if "result" in e else "—"
        return line("RESULT", f"{e.get('name', '?')} {e.get('status', '?')} {lat_s} {res}")
    if typ == "transfer":
        return line("TRANSFER", f"{e.get('target', '?')} → {e.get('status', '?')}")
    if typ == "route":
        return line("ROUTE", str(e.get("target", "?")), stamp=" " * 6)
    if typ == "hangup":
        return line("HANGUP", f"by {e.get('by', '?')}")
    return line(str(typ).upper(), dumps(rest))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", default="data/labeled_sample.jsonl")
    ap.add_argument("--out", default="docs/labeled_sample.md")
    a = ap.parse_args()

    calls = []
    with open(a.input, encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                calls.append(json.loads(ln))

    counts = Counter(c.get("label", "?") for c in calls)
    order = sorted(counts, key=lambda k: (-counts[k], k))
    out = ["# Labeled sample (hand-labeled calls)", "",
           f"Total calls: {len(calls)}", "",
           "| label | count |", "|---|---:|"]
    out += [f"| {l} | {counts[l]} |" for l in order]
    out += ["", "## Calls with a note", "", "| call_id | label | note |", "|---|---|---|"]
    for c in calls:
        if c.get("note"):
            note = str(c["note"]).replace("|", "\\|").replace("\n", " ")
            out.append(f"| {c.get('call_id')} | {c.get('label')} | {note} |")
    for l in order:
        out += ["", f"## {l} ({counts[l]})"]
        for c in calls:
            if c.get("label", "?") != l:
                continue
            out += ["", f"### {c.get('call_id')} — {l}", ""]
            if c.get("note"):
                out += [f"> {c['note']}", ""]
            out.append("```text")
            out += [fmt_event(e) for e in c.get("events", [])]
            out.append("```")
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
