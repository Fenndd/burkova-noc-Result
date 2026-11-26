"""Tests for classify.py (spec: docs/spec_task1_eval.md, edition 5).

Run:  python -m unittest discover -s tests
Synthetic calls are named after the decision ids of docs/contested_cases.md.
"""
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import classify  # noqa: E402

DATA = os.path.join(ROOT, "data")


# ---------------------------------------------------------------- event builders

def bot(t, text="..."):
    return {"t": t, "type": "bot", "text": text}


def caller(t, text="..."):
    return {"t": t, "type": "caller", "text": text, "asr_conf": 0.9}


def call(t, name, **args):
    return {"t": t, "type": "tool_call", "name": name, "args": args}


def res(t, name, status, result=None):
    e = {"t": t, "type": "tool_result", "name": name, "status": status, "latency_ms": 100}
    if result is not None:
        e["result"] = result
    return e


def hang(t, by):
    return {"t": t, "type": "hangup", "by": by}


def xfer(t, status, target="dispatch"):
    return {"t": t, "type": "transfer", "target": target, "status": status}


def route(t, target="customer_line"):
    return {"t": t, "type": "route", "target": target}


GREET = bot(0.0, "Dobry vecer")
KNOWN = {"outage_id": "O-1", "eta": "2026-11-16T02:00:00+01:00"}
NONE_OUT = {"outage_id": None}
RES_OK = {"address_id": "A-1"}
# address resolved and confirmed, get_outage called; the test appends the result
ADDR = [GREET, caller(7), call(7.5, "resolve_address", text="x"), res(7.9, "resolve_address", "ok", RES_OK),
        bot(7.9, "Overim si"), caller(11, "ano"), call(11.5, "get_outage", address_id="A-1")]
# ... same, but unknown outage: bot asks for a description
UNKNOWN = ADDR + [res(13, "get_outage", "ok", NONE_OUT), bot(13, "Opiste")]
TICKET = [caller(16, "nejde elektrina"), call(17, "create_ticket", address_id="A-1", description="d")]


def failed_resolve(t0, status="no_match"):
    return [caller(t0), call(t0 + 0.5, "resolve_address", text="x"), res(t0 + 1, "resolve_address", status),
            bot(t0 + 1, "Nerozumiem")]


def lab(events):
    return classify.classify_call({"call_id": "x", "events": events})


class Base(unittest.TestCase):
    def check(self, expected, events, msg=None):
        self.assertEqual(lab(events), expected, msg)


# ---------------------------------------------------------------- section 4 cases

class TestA(Base):
    def test_A1_late_ok_is_ended_early(self):
        self.check("ENDED_EARLY", ADDR + [hang(13, "caller"), res(14, "get_outage", "ok", KNOWN)])

    def test_A1_late_timeout_is_api_error(self):
        self.check("API_ERROR", ADDR + [hang(13, "caller"), res(16, "get_outage", "timeout")])

    def test_A1_no_result_is_api_error(self):
        self.check("API_ERROR", ADDR + [hang(13, "caller")])

    def test_A2_address_rejected_by_caller(self):
        ev = [GREET, caller(7), call(7.5, "resolve_address", text="x"), res(8, "resolve_address", "ok", RES_OK),
              bot(8), caller(11, "nie"), call(12, "resolve_address", text="y"),
              res(12.4, "resolve_address", "ok", RES_OK), bot(12.4), caller(15, "nie nie"), bot(16, "Prepacte"),
              hang(17, "bot")]
        self.check("ADDRESS_NOT_UNDERSTOOD", ev)

    def test_A4_retry_then_success(self):
        # no_match, then ambiguous, then ok; get_outage ok and known; the bot speaks; all in time order
        ev = [GREET] + failed_resolve(7, "no_match") + failed_resolve(14, "ambiguous") + [
            caller(21), call(21.5, "resolve_address", text="z"), res(21.9, "resolve_address", "ok", RES_OK),
            bot(21.9, "Overim si"), caller(25, "ano"), call(25.5, "get_outage", address_id="A-1"),
            res(27, "get_outage", "ok", KNOWN), bot(27, "Evidujeme poruchu"), hang(33, "bot")]
        times = [e["t"] for e in ev]
        self.assertEqual(times, sorted(times))
        self.check("KNOWN_OUTAGE_INFORMED", ev)

    def test_A5_hangup_at_greeting(self):
        self.check("ENDED_EARLY", [GREET, hang(3.4, "caller")])

    def test_A5_caller_said_halo_bot_silent(self):
        self.check("ENDED_EARLY", [GREET, caller(7, "halo"), hang(10, "caller")])

    def test_known_informed_basic(self):
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13), hang(20, "bot")])

    def test_ticket_basic(self):
        self.check("TICKET_CREATED", UNKNOWN + TICKET + [res(17.5, "create_ticket", "ok", {"ticket_id": "T-1"}),
                                                        bot(17.5), hang(25, "caller")])

    def test_transferred_and_failed(self):
        base = [GREET, caller(8, "drot"), bot(10, "Prepajam")]
        self.check("TRANSFERRED", base + [xfer(28, "connected"), hang(28.1, "system")])
        self.check("TRANSFER_FAILED", base + [xfer(28, "queue_full"), bot(28), hang(30, "bot")])
        self.check("TRANSFER_FAILED", base + [xfer(28, "timeout"), bot(28), hang(30, "bot")])

    def test_route_basic(self):
        self.check("OUT_OF_SCOPE", [GREET, caller(7, "faktura"), bot(9), route(9.5), hang(14, "caller")])


class TestB(Base):
    def test_B1_no_match_then_caller_hangs_up(self):
        self.check("ADDRESS_NOT_UNDERSTOOD", [GREET] + failed_resolve(7) + [hang(12, "caller")])

    def test_B1_resolve_without_result(self):
        self.check("ADDRESS_NOT_UNDERSTOOD", [GREET, caller(7), call(7.5, "resolve_address", text="x"),
                                              hang(8, "caller")])

    # N1: a network drop before any outcome is ENDED_EARLY, whatever failed before
    def test_N1_network_after_single_no_match(self):
        self.check("ENDED_EARLY", [GREET] + failed_resolve(7) + [hang(15, "network")])

    def test_N1_network_after_several_failed_attempts(self):
        self.check("ENDED_EARLY", [GREET] + failed_resolve(7) + failed_resolve(12, "ambiguous")
                   + [hang(20, "network")])

    def test_N1_network_after_resolved_address(self):
        self.check("ENDED_EARLY", [GREET, caller(7), call(7.5, "resolve_address", text="x"),
                                   res(7.9, "resolve_address", "ok", RES_OK), bot(7.9, "Sedi to?"),
                                   caller(11, "hej"), hang(11.5, "network")])

    def test_N1_network_while_waiting_for_get_outage(self):
        self.check("ENDED_EARLY", ADDR + [hang(13, "network")])

    def test_N1_network_after_failed_get_outage(self):
        self.check("ENDED_EARLY", ADDR + [res(13, "get_outage", "error"), bot(13, "overujem"),
                                          hang(16, "network")])

    def test_N1_network_after_failed_ticket(self):
        self.check("ENDED_EARLY", UNKNOWN + TICKET + [res(18, "create_ticket", "error"),
                                                      hang(19, "network")])

    def test_N1_outcome_before_drop_is_kept(self):
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13, "Porucha"),
                                                    hang(20, "network")])
        self.check("TICKET_CREATED", UNKNOWN + TICKET + [res(18, "create_ticket", "ok", {"ticket_id": "T-1"}),
                                                         bot(18, "Hotovo"), hang(20, "network")])
        self.check("TRANSFER_FAILED", [GREET, caller(7), bot(8), xfer(30, "no_agents"), bot(30),
                                       hang(33, "network")])
        self.check("OUT_OF_SCOPE", [GREET, caller(7, "faktura"), bot(9), route(9.5), hang(14, "network")])

    def test_N1_caller_hangup_rules_unchanged(self):
        self.check("ADDRESS_NOT_UNDERSTOOD", [GREET] + failed_resolve(7) + [hang(15, "caller")])
        self.check("API_ERROR", ADDR + [hang(13, "caller")])

    def test_B1_many_attempts_not_hardcoded(self):
        ev = [GREET]
        for k in range(5):
            ev += failed_resolve(7 + 5 * k, "ambiguous")
        self.check("ADDRESS_NOT_UNDERSTOOD", ev + [hang(40, "bot")])

    def test_B2_unknown_outage_caller_leaves_before_ticket(self):
        self.check("ENDED_EARLY", UNKNOWN + [hang(16, "caller")])

    def test_B3_ticket_ok_after_hangup(self):
        ev = UNKNOWN + TICKET + [hang(17.2, "caller"), res(18, "create_ticket", "ok", {"ticket_id": "T-1"})]
        self.check("TICKET_CREATED", ev)

    def test_B4_ticket_no_result_or_timeout(self):
        self.check("API_ERROR", UNKNOWN + TICKET + [hang(20, "caller")])
        self.check("API_ERROR", UNKNOWN + TICKET + [res(20, "create_ticket", "timeout"), bot(20), hang(22, "bot")])
        self.check("API_ERROR", UNKNOWN + TICKET + [hang(20, "caller"), res(23, "create_ticket", "timeout")])

    def test_B5_retry_after_timeout(self):
        retry = [res(19.5, "get_outage", "timeout"), bot(19.5, "Skusim znova"), call(20, "get_outage", address_id="A-1")]
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + retry + [res(21, "get_outage", "ok", KNOWN), bot(21),
                                                            hang(28, "bot")])
        self.check("TICKET_CREATED", ADDR + retry + [res(21, "get_outage", "ok", NONE_OUT), bot(21),
                                                     caller(24), call(25, "create_ticket", address_id="A-1"),
                                                     res(25.4, "create_ticket", "ok", {"ticket_id": "T"}),
                                                     bot(25.4), hang(30, "bot")])

    def test_B6_last_transfer_decides(self):
        base = [GREET, caller(8, "drot")]
        self.check("TRANSFERRED", base + [xfer(30, "queue_full"), bot(30), xfer(60, "connected"), hang(60.1, "system")])
        self.check("TRANSFER_FAILED", base + [xfer(30, "connected"), xfer(40, "queue_full"), hang(41, "bot")])

    def test_B7_unknown_get_outage_status(self):
        # payload + bot spoke right after -> success
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [res(13, "get_outage", "degraded", KNOWN), bot(13),
                                                    hang(20, "bot")])
        # error status, outage_id null, bot apologises, no ticket/transfer -> failure
        self.check("API_ERROR", ADDR + [res(13, "get_outage", "error", {"outage_id": None, "error": "503"}),
                                        bot(13, "Prepacte"), hang(15, "caller")])
        # no payload at all
        self.check("API_ERROR", ADDR + [res(13, "get_outage", "rate_limited"), bot(13), hang(15, "bot")])
        # payload but the call was repeated -> not a success; last attempt decides
        self.check("API_ERROR", ADDR + [res(13, "get_outage", "503", KNOWN), call(14, "get_outage", address_id="A-1"),
                                        res(16, "get_outage", "503"), bot(16), hang(18, "bot")])
        # outage_id null with a non-ok status but the flow went on to a ticket -> "no outage"
        self.check("TICKET_CREATED", ADDR + [res(13, "get_outage", "partial", NONE_OUT), bot(13)] + TICKET + [
            res(17.5, "create_ticket", "ok", {"ticket_id": "T"}), bot(17.5), hang(25, "caller")])

    def test_B7_unknown_ticket_status(self):
        ok = [res(17.5, "create_ticket", "created", {"ticket_id": "T-1"}), bot(17.5), hang(25, "caller")]
        self.check("TICKET_CREATED", UNKNOWN + TICKET + ok)
        bad = [res(17.5, "create_ticket", "error"), bot(17.5), hang(25, "bot")]
        self.check("API_ERROR", UNKNOWN + TICKET + bad)
        silent = [res(17.5, "create_ticket", "created", {"ticket_id": "T-1"}), hang(25, "bot")]
        self.check("API_ERROR", UNKNOWN + TICKET + silent)  # no spoken result -> not a success

    def test_B7_status_case_insensitive(self):
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [res(13, "get_outage", " OK ", KNOWN), bot(13), hang(20, "bot")])
        self.check("TRANSFERRED", [GREET, caller(8), xfer(30, "Connected"), hang(30.1, "system")])

    def test_B8_unknown_resolve_status_is_address_never_api_error(self):
        self.check("ADDRESS_NOT_UNDERSTOOD", [GREET] + failed_resolve(7, "low_confidence") + [hang(12, "bot")])
        self.check("ADDRESS_NOT_UNDERSTOOD", [GREET] + failed_resolve(7, "error") + [hang(12, "caller")])
        # empty candidates are no evidence of success
        ev = [GREET, caller(7), call(7.5, "resolve_address", text="x"),
              res(8, "resolve_address", "weird", {"candidates": []}), bot(8), hang(12, "bot")]
        self.check("ADDRESS_NOT_UNDERSTOOD", ev)

    def test_B8_unknown_resolve_status_with_evidence_is_success(self):
        ev = [GREET, caller(7), call(7.5, "resolve_address", text="x"),
              res(8, "resolve_address", "low_confidence", RES_OK), bot(8), caller(11),
              call(11.5, "get_outage", address_id="A-1"), res(13, "get_outage", "ok", KNOWN), bot(13),
              hang(20, "bot")]
        self.check("KNOWN_OUTAGE_INFORMED", ev)

    def test_B8_unknown_resolve_status_with_payload_but_retry_is_failure(self):
        ev = [GREET, caller(7), call(7.5, "resolve_address", text="x"),
              res(8, "resolve_address", "low_confidence", RES_OK), bot(8), caller(11),
              call(12, "resolve_address", text="y"), res(12.5, "resolve_address", "no_match"), bot(12.5),
              hang(15, "caller")]
        self.check("ADDRESS_NOT_UNDERSTOOD", ev)

    def test_B9_new_transfer_status(self):
        for st in ("busy", "rejected", "no_answer", "", "abandoned"):
            self.check("TRANSFER_FAILED", [GREET, caller(8), xfer(30, st), hang(31, "bot")], st)

    def test_B10_new_route_target(self):
        for tgt in ("web", "sms", "billing_line", "customer_line"):
            self.check("OUT_OF_SCOPE", [GREET, caller(7, "faktura"), bot(9), route(9.5, tgt), hang(14, "caller")])

    def test_B11_no_eta(self):
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [res(13, "get_outage", "ok", {"outage_id": "O-9"}), bot(13),
                                                    hang(20, "caller")])

    def test_B12_known_result_but_bot_silent(self):
        for by in ("bot", "caller", "system"):
            self.check("API_ERROR", ADDR + [res(13, "get_outage", "ok", KNOWN), hang(14, by)], by)

    def test_B13_unknown_outage_bot_ends_without_ticket(self):
        self.check("API_ERROR", UNKNOWN + [hang(16, "bot")])
        self.check("API_ERROR", UNKNOWN + [hang(16, "system")])
        self.check("ENDED_EARLY", UNKNOWN + [hang(16, "network")])  # new hangup.by value

    def test_B14_unknown_tool_is_ignored(self):
        sms = [call(14, "send_sms"), res(22, "send_sms", "timeout"), bot(22), hang(23, "bot")]
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13)] + sms)
        # unknown tool failing before any outcome does not make API_ERROR
        self.check("ENDED_EARLY", [GREET, caller(7), call(8, "lookup_customer"),
                                   res(9, "lookup_customer", "error"), hang(10, "caller")])
        # unknown event type between the result and the bot is skipped
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [res(13, "get_outage", "ok", KNOWN),
                                                    {"t": 13.0, "type": "tts_start"}, bot(13), hang(20, "bot")])
        # caller barge-in between result and bot is skipped
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [res(13, "get_outage", "ok", KNOWN), caller(13.2, "halo"),
                                                    bot(13.5), hang(20, "caller")])

    def test_B16_last_episode_wins(self):
        paid = UNKNOWN + TICKET + [res(17.5, "create_ticket", "ok", {"ticket_id": "T"}), bot(17.5)]
        self.check("OUT_OF_SCOPE", paid + [route(20), hang(25, "caller")])
        known = ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13)]
        self.check("OUT_OF_SCOPE", known + [caller(15, "a faktura"), route(17), hang(20, "caller")])
        self.check("TICKET_CREATED", [GREET, caller(7, "faktura"), route(9)] + ADDR[2:] + [
            res(13, "get_outage", "ok", NONE_OUT), bot(13)] + TICKET + [
            res(17.5, "create_ticket", "ok", {"ticket_id": "T"}), bot(17.5), hang(25, "caller")])

    def test_B17_ticket_then_failed_transfer(self):
        ev = UNKNOWN + TICKET + [res(17.5, "create_ticket", "ok", {"ticket_id": "T"}), bot(17.5),
                                 xfer(40, "queue_full"), bot(40), hang(45, "bot")]
        self.check("TRANSFER_FAILED", ev)

    def test_B17_failed_transfer_then_ticket(self):
        ev = [GREET, caller(3, "drot"), bot(4), xfer(5, "queue_full"), bot(5.5, "adresa?")] + ADDR[2:] + [
            res(13, "get_outage", "ok", NONE_OUT), bot(13)] + TICKET + [
            res(17.5, "create_ticket", "ok", {"ticket_id": "T"}), bot(17.5), hang(25, "caller")]
        self.check("TRANSFER_FAILED", ev)


class TestR(Base):
    def test_R1_repeated_connected_stays_transferred(self):
        ev = UNKNOWN + TICKET + [res(17.5, "create_ticket", "ok", {"ticket_id": "T"}), bot(17.5),
                                 xfer(40, "connected"), xfer(41, "connected"), hang(42, "system")]
        self.check("TRANSFERRED", ev)

    def test_R2_first_hangup_ends_the_call(self):
        late = [hang(13, "caller"), res(14, "get_outage", "ok", KNOWN), bot(14, "Evidujeme"), hang(14.1, "system")]
        self.check("ENDED_EARLY", ADDR + late)

    def test_R2_first_hangup_by_is_used(self):
        self.check("ENDED_EARLY", UNKNOWN + [hang(16, "caller"), hang(17, "bot")])

    def test_R3_results_pair_with_calls_in_order(self):
        ev = ADDR + [res(14, "get_outage", "timeout"), call(15, "get_outage", address_id="A-1"),
                     res(16, "get_outage", "timeout"), call(17, "get_outage", address_id="A-1"),
                     res(18, "get_outage", "ok", KNOWN), bot(18), hang(25, "bot")]
        self.check("KNOWN_OUTAGE_INFORMED", ev)

    def test_R4_renamed_result_field_is_not_supported(self):
        # documented limitation: no outage_id -> read as "no known outage"; bot hangs up -> B13
        ev = ADDR + [res(13, "get_outage", "ok", {"outages": [{"id": "O"}]}), bot(13), hang(20, "bot")]
        self.check("API_ERROR", ev)

    def test_R5_single_resolve_bot_or_system_gave_up(self):
        for by in ("bot", "system"):
            ev = [GREET, caller(7), call(7.5, "resolve_address", text="x"),
                  res(8, "resolve_address", "ok", RES_OK), bot(8), caller(11, "nie"), bot(12), hang(13, by)]
            self.check("ADDRESS_NOT_UNDERSTOOD", ev, by)

    def test_R5_single_resolve_caller_left_is_ended_early(self):
        ev = [GREET, caller(7), call(7.5, "resolve_address", text="x"),
              res(8, "resolve_address", "ok", RES_OK), bot(8), hang(10, "caller")]
        self.check("ENDED_EARLY", ev)

    def test_R6_route_after_failure_does_not_mean_out_of_scope(self):
        timeout = ADDR + [res(19.5, "get_outage", "timeout"), bot(19.5, "Prepacte")]
        self.check("API_ERROR", timeout + [route(20, "callback"), hang(25, "caller")])
        self.check("ADDRESS_NOT_UNDERSTOOD", [GREET] + failed_resolve(7) + [route(13), hang(16, "caller")])
        # a fixed failure followed by a route is out of scope again
        self.check("OUT_OF_SCOPE", [GREET] + failed_resolve(7) + ADDR[2:5] + [
            call(12, "get_outage", address_id="A-1"), res(13, "get_outage", "ok", KNOWN), bot(13), route(15),
            hang(18, "caller")])

    def test_R7_caller_gave_up_waiting_for_dispatcher(self):
        base = [GREET, caller(7, "drot"), bot(9, "Prepajam vas na dispecing"), hang(40, "caller")]
        self.check("ENDED_EARLY", base)
        self.check("ENDED_EARLY", base + [xfer(41, "abandoned")])
        self.check("ENDED_EARLY", base + [xfer(41, "connected")])  # late transfer never changes the label
        # a ticket created earlier still counts (step 2)
        ev = UNKNOWN + TICKET + [res(17.5, "create_ticket", "ok", {"ticket_id": "T"}), bot(17.5),
                                 hang(40, "caller"), xfer(41, "queue_full")]
        self.check("TICKET_CREATED", ev)

    def test_S04_direct_transfer_fails_then_status_announced(self):
        ev = [GREET, caller(7, "iskri"), bot(9, "Prepajam"), xfer(30, "queue_full"), bot(30, "adresa?"),
              caller(35), call(35.5, "resolve_address", text="x"), res(36, "resolve_address", "ok", RES_OK),
              bot(36), caller(39), call(39.5, "get_outage", address_id="A-1"),
              res(41, "get_outage", "ok", KNOWN), bot(41, "Evidujeme"), hang(48, "bot")]
        self.check("TRANSFER_FAILED", ev)

    def test_S03_failed_then_connected_transfer(self):
        ev = UNKNOWN + TICKET + [res(19.5, "create_ticket", "ok", {"ticket_id": "T"}), bot(19.5),
                                 xfer(40, "queue_full"), bot(40), xfer(70, "connected"), hang(70.1, "system")]
        self.check("TRANSFERRED", ev)

    def test_S_get_outage_timeout_then_ticket_fallback(self):
        ev = ADDR + [res(19.5, "get_outage", "timeout"), bot(19.5), call(20, "create_ticket", address_id="A-1"),
                     res(20.5, "create_ticket", "ok", {"ticket_id": "T-1"}), bot(20.5), hang(27, "caller")]
        self.check("TICKET_CREATED", ev)

    def test_S_equal_t_keeps_file_order(self):
        # result, hangup, bot all at t=13: the bot line is logged after the hangup -> did not speak (B12)
        self.check("API_ERROR", ADDR + [res(13, "get_outage", "ok", KNOWN), hang(13, "caller"), bot(13)])
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13), hang(13, "caller")])

    def test_S_transfer_to_other_target_connected(self):
        ev = [GREET, caller(7, "faktura"), bot(9), xfer(30, "connected", target="customer_line"), hang(30.1, "system")]
        self.check("TRANSFERRED", ev)

    def test_S_result_is_a_list_does_not_crash(self):
        self.check("API_ERROR", ADDR + [res(13, "get_outage", "ok", ["O-1"]), bot(13), hang(20, "bot")])


# ---------------------------------------------------------------- 5.2 malformed data

class TestMalformed(Base):
    def test_no_hangup_end_is_last_event(self):
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13)])
        self.check("ENDED_EARLY", [GREET])

    def test_unsorted_events(self):
        self.check("KNOWN_OUTAGE_INFORMED", [hang(20, "bot")] + ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13)])

    def test_missing_type_is_inferred(self):
        strip = lambda e: {k: v for k, v in e.items() if k != "type"}  # noqa: E731
        ev = [strip(e) for e in ADDR[1:]] + [strip(res(13, "get_outage", "ok", KNOWN)), bot(13), strip(hang(20, "bot"))]
        self.check("KNOWN_OUTAGE_INFORMED", [GREET] + ev)
        self.check("TRANSFER_FAILED", [GREET, strip(xfer(30, "queue_full")), strip(hang(31, "bot"))])
        self.check("OUT_OF_SCOPE", [GREET, strip(route(9)), strip(hang(12, "caller"))])

    def test_result_not_a_dict(self):
        for r in ("string", 5, [], None, True):
            ev = ADDR + [{"t": 13, "type": "tool_result", "name": "get_outage", "status": "ok", "result": r},
                         bot(13), hang(20, "caller")]
            # `ok` without a usable outage_id = no known outage; the caller leaves -> B2
            self.check("ENDED_EARLY", ev, repr(r))
        ev = [GREET, caller(7), call(7.5, "resolve_address", text="x"),
              {"t": 8, "type": "tool_result", "name": "resolve_address", "status": "weird", "result": "boom"},
              hang(9, "bot")]
        self.check("ADDRESS_NOT_UNDERSTOOD", ev)

    def test_t_as_string_or_missing(self):
        ev = [dict(e) for e in ADDR] + [res(13, "get_outage", "ok", KNOWN), bot(13), hang(20, "bot")]
        for e in ev:
            e["t"] = str(e["t"])
        self.check("KNOWN_OUTAGE_INFORMED", ev)
        ev2 = [dict(e) for e in ev]
        del ev2[-2]["t"]  # the bot line without t takes the previous t (13.0)
        del ev2[-1]["t"]
        self.check("KNOWN_OUTAGE_INFORMED", ev2)
        ev3 = [dict(e) for e in ev]
        ev3[3]["t"] = "abc"  # invalid t = the previous event's t (7.5), the order is unchanged
        self.check("KNOWN_OUTAGE_INFORMED", ev3)

    def test_non_dict_events_are_skipped(self):
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + [None, "x", 5, res(13, "get_outage", "ok", KNOWN), bot(13),
                                                    hang(20, "bot")])

    def test_unknown_event_types_and_values_do_not_crash(self):
        ev = [GREET, {"t": 1, "type": "dtmf", "digit": "5"}, {"t": 2, "type": "tool_call", "name": "x", "args": 1},
              {"t": 3, "type": "tool_result"}, {"t": 4, "type": "transfer"}, {"t": 5, "type": "hangup"}]
        # the nameless tool_result is ignored (B14); the transfer has no `connected` status (B9)
        self.check("TRANSFER_FAILED", ev)

    def test_fallback_for_unusable_events(self):
        for events in (None, "x", 5, {}, []):
            self.assertEqual(lab(events), classify.FALLBACK)
        self.assertEqual(classify.classify_call({}), classify.FALLBACK)
        self.assertEqual(lab([None, 5]), classify.FALLBACK)


def run_file(lines, bom=False):
    """Run classify.run on a temp file; return (rows, stderr text)."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "in.jsonl")
        data = "\n".join(lines) + "\n"
        with open(p, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
            f.write(data)
        out, err = io.StringIO(), []
        classify.run(p, out, err.append)
    rows = [r for r in csv.reader(io.StringIO(out.getvalue(), newline="")) if r]
    return rows, "\n".join(err)


class TestFile(unittest.TestCase):
    def good(self, cid, events):
        return json.dumps({"call_id": cid, "events": events})

    def test_one_row_per_line_in_order_with_bad_lines(self):
        known = ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13), hang(20, "bot")]
        trunc = self.good("c-trunc", known)[:-30]  # cut inside the hangup event, JSON is broken
        lines = [
            self.good("c-1", known),
            "",
            "   ",
            "this is not json at all",                              # no call_id -> line-N
            trunc,
            '{"call_id": "c-nolist", "events": "oops"}',
            '{"call_id": "c-empty", "events": []}',
            json.dumps({"call_id": "c-nokey"}),
            json.dumps([1, 2, 3]),
            json.dumps({"events": known}),                          # no call_id -> line-N
            self.good("c-1", [GREET, hang(3, "caller")]),           # duplicate call_id kept
            self.good("c-3", [GREET, hang(3, "caller")]),
        ]
        rows, err = run_file(lines)
        self.assertEqual(rows[0], ["call_id", "label"])
        got = rows[1:]
        ids = [r[0] for r in got]
        self.assertEqual(ids, ["c-1", "line-4", "c-trunc", "c-nolist", "c-empty", "c-nokey", "line-9", "line-10",
                               "c-1", "c-3"])
        labels = [r[1] for r in got]
        self.assertTrue(all(l in classify.LABELS for l in labels))
        self.assertEqual(labels[0], "KNOWN_OUTAGE_INFORMED")
        self.assertEqual(labels[2], "KNOWN_OUTAGE_INFORMED")  # recovered events, no hangup -> last event
        self.assertEqual(labels[3:8], [classify.FALLBACK] * 5)
        self.assertEqual(labels[8:], ["ENDED_EARLY", "ENDED_EARLY"])
        self.assertIn("c-trunc", err)  # recovery is logged

    def test_bom(self):
        rows, _ = run_file([json.dumps({"call_id": "c-1", "events": [GREET, hang(3, "caller")]})], bom=True)
        self.assertEqual(rows[1], ["c-1", "ENDED_EARLY"])

    def test_summary_reports_unseen_values(self):
        ev = ADDR + [res(13, "get_outage", "weird_status", KNOWN), bot(13), call(14, "send_sms"),
                     {"t": 15, "type": "dtmf"}, route(16, "web"), xfer(17, "busy"), hang(20, "network")]
        _, err = run_file([self.good("c-1", ev)])
        for needle in ("weird_status", "send_sms", "dtmf", "web", "busy", "network"):
            self.assertIn(needle, err)
        _, err2 = run_file([self.good("c-1", ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13), hang(20, "bot")])])
        self.assertIn("(none)", err2)


# ---------------------------------------------------------------- review fixes 1-9

class TestFixes(Base):
    def test_fix1_ticket_timeout_then_route_is_api_error(self):
        t = UNKNOWN + TICKET
        self.check("API_ERROR", t + [res(17.5, "create_ticket", "timeout"), bot(17.5), route(18), hang(20, "caller")])
        self.check("API_ERROR", t + [route(18), hang(20, "caller")])  # no result at all
        # a ticket that succeeded before the route does not block OUT_OF_SCOPE
        self.check("OUT_OF_SCOPE", t + [res(17.5, "create_ticket", "ok", {"ticket_id": "T"}), bot(17.5),
                                        route(18), hang(20, "caller")])

    def test_fix2_unsorted_input_equal_t_is_ordered_causally(self):
        tail = [res(13, "get_outage", "ok", KNOWN), bot(13)]
        self.check("KNOWN_OUTAGE_INFORMED", ADDR + tail + [hang(20, "bot")])  # sorted reference
        shuffled = [hang(20, "bot")] + [bot(13), res(13, "get_outage", "ok", KNOWN)] + ADDR
        self.check("KNOWN_OUTAGE_INFORMED", shuffled)
        rev = list(reversed(ADDR + tail + [hang(20, "bot")]))
        self.check("KNOWN_OUTAGE_INFORMED", rev)

    def test_fix2_sorted_input_keeps_file_order(self):
        # the bot line logged before the result at equal t: the result has no spoken status -> B12
        self.check("API_ERROR", ADDR + [bot(13), res(13, "get_outage", "ok", KNOWN), hang(20, "bot")])

    def test_fix3_typeless_bot_line(self):
        ev = ADDR + [res(13, "get_outage", "ok", KNOWN), {"t": 13, "text": "Evidujeme poruchu"}, hang(20, "caller")]
        self.check("KNOWN_OUTAGE_INFORMED", ev)
        # a typeless line WITH asr_conf is still the caller, not the bot
        ev = ADDR + [res(13, "get_outage", "ok", KNOWN), {"t": 13, "text": "halo", "asr_conf": 0.8}, hang(20, "caller")]
        self.check("API_ERROR", ev)

    def test_fix7_boolean_false_is_no_id(self):
        self.check("ENDED_EARLY", ADDR + [res(13, "get_outage", "ok", {"outage_id": False}), bot(13),
                                          hang(20, "caller")])
        self.assertFalse(classify.nonempty(False))
        self.assertTrue(classify.nonempty(0))
        ev = [GREET, caller(7), call(7.5, "resolve_address", text="x"),
              res(8, "resolve_address", "weird", {"address_id": False}), bot(8), hang(12, "bot")]
        self.check("ADDRESS_NOT_UNDERSTOOD", ev)
        ev = UNKNOWN + TICKET + [res(17.5, "create_ticket", "created", {"ticket_id": False}), bot(17.5),
                                 hang(25, "bot")]
        self.check("API_ERROR", ev)

    def test_decisionA_ticket_while_outage_known_is_ignored(self):
        ev = ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13, "Evidujeme poruchu"), caller(16, "nahlasit"),
                     call(17, "create_ticket", address_id="A-1"), res(17.5, "create_ticket", "ok", {"ticket_id": "T"}),
                     bot(17.5), hang(25, "caller")]
        self.check("KNOWN_OUTAGE_INFORMED", ev)

    def test_decisionA_unknown_outage_ticket_still_counts(self):
        self.check("TICKET_CREATED", UNKNOWN + TICKET + [res(17.5, "create_ticket", "ok", {"ticket_id": "T"}),
                                                         bot(17.5), hang(25, "caller")])

    def test_decisionB_ticket_created_after_hangup(self):
        late = [hang(16, "caller"), call(17, "create_ticket", address_id="A-1", description="d")]
        self.check("TICKET_CREATED", UNKNOWN + late + [res(18, "create_ticket", "ok", {"ticket_id": "T-1"})])
        # same call, the ticket timed out: nobody was helped, unknown outage + caller left -> B2
        self.check("ENDED_EARLY", UNKNOWN + late + [res(18, "create_ticket", "timeout")])
        self.check("ENDED_EARLY", UNKNOWN + late)  # no result at all
        # other late calls stay ignored
        self.check("ENDED_EARLY", ADDR + [hang(13, "caller"), call(14, "get_outage", address_id="A-1"),
                                          res(15, "get_outage", "ok", NONE_OUT)])

    def test_decisionB_with_decisionA(self):
        known = ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13)]
        late = [hang(16, "caller"), call(17, "create_ticket", address_id="A-1"),
                res(18, "create_ticket", "ok", {"ticket_id": "T"})]
        self.check("KNOWN_OUTAGE_INFORMED", known + late)

    def test_decisionB_late_ticket_does_not_steal_earlier_result(self):
        # the call at 17 got no result before the hangup; the result at 18 belongs to it (B3)
        ev = UNKNOWN + TICKET + [hang(17.2, "caller"), call(17.5, "create_ticket", address_id="A-1"),
                                 res(18, "create_ticket", "ok", {"ticket_id": "T"})]
        self.check("TICKET_CREATED", ev)


def bytes_run(raw_lines):
    """Run classify.run on raw byte lines; return the csv-parsed rows."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "in.jsonl")
        with open(p, "wb") as f:
            f.write(b"".join(raw_lines))
        out = io.StringIO()
        classify.run(p, out, lambda m: None)
    return [r for r in csv.reader(io.StringIO(out.getvalue(), newline="")) if r]


class TestFixesFile(unittest.TestCase):
    def good(self, cid, events):
        return json.dumps({"call_id": cid, "events": events})

    def test_fix5_lone_cr_inside_a_line_is_one_row(self):
        known = ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13), hang(20, "bot")]
        line = self.good("c-cr", known).replace('"events"', '\r"events"')  # CR as JSON whitespace
        self.assertIn("\r", line)
        crlf = self.good("c-2", [GREET, hang(3, "caller")]) + "\r"  # a CRLF-terminated line still works
        rows, _ = run_file([line, crlf])
        self.assertEqual(rows, [["call_id", "label"], ["c-cr", "KNOWN_OUTAGE_INFORMED"], ["c-2", "ENDED_EARLY"]])

    def test_fix6_escaped_call_id_in_broken_line(self):
        cid = 'c"x\\y-\u010d'
        known = ADDR + [res(13, "get_outage", "ok", KNOWN), bot(13), hang(20, "bot")]
        broken = self.good(cid, known)[:-30]
        self.assertIn('\\"', broken)  # the call_id is still JSON-escaped in the raw text
        rows, _ = run_file([broken])
        self.assertEqual(rows[1][0], cid)
        self.assertEqual(rows[1][1], "KNOWN_OUTAGE_INFORMED")

    def test_csv_quoting_of_call_id_with_comma_and_quote(self):
        cid = 'a,"b",c'
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "in.jsonl")
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(self.good(cid, [GREET, hang(3, "caller")]) + "\n")
            out = io.StringIO()
            classify.run(p, out, lambda m: None)
        self.assertEqual(out.getvalue(), 'call_id,label\n"a,""b"",c",ENDED_EARLY\n')
        self.assertEqual(list(csv.reader(io.StringIO(out.getvalue())))[1], [cid, "ENDED_EARLY"])

    def test_non_utf8_bytes_in_a_line(self):
        ok = (self.good("c-1", [GREET, hang(3, "caller")]) + "\n").encode("utf-8")
        garbage = b"\xff\xfe\x00\x80 not json \xc3\x28\n"  # no JSON at all -> one fallback row
        # an invalid byte inside a JSON string value: the line is still parsed normally
        inside = (self.good("c-in", [GREET, hang(3, "caller")]) + "\n").encode("utf-8").replace(b"c-in", b"c-\xe9n")
        rows = bytes_run([ok, garbage, inside, ok])
        self.assertEqual(len(rows), 5)  # header + one row per line
        self.assertEqual(rows[2], ["line-2", classify.FALLBACK])
        self.assertEqual([r[1] for r in rows[1:]][0::2], ["ENDED_EARLY"] * 2)
        self.assertEqual(rows[3][1], "ENDED_EARLY")


# ---------------------------------------------------------------- regression on the real data

class TestRegression(unittest.TestCase):
    def test_labeled_sample_60_of_60(self):
        n = bad = 0
        with open(os.path.join(DATA, "labeled_sample.jsonl"), encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                n += 1
                if classify.classify_call(r) != r["label"]:
                    bad += 1
                    print("mismatch", r["call_id"])
        self.assertEqual((n, bad), (60, 0))

    def test_night1_distribution_and_order(self):
        path = os.path.join(DATA, "transcripts.jsonl")
        out = io.StringIO()
        classify.run(path, out, lambda m: None)
        rows = [r.split(",") for r in out.getvalue().split("\n") if r]
        self.assertEqual(rows[0], ["call_id", "label"])
        with open(path, encoding="utf-8") as f:
            ids = [json.loads(l)["call_id"] for l in f if l.strip()]
        self.assertEqual([r[0] for r in rows[1:]], ids)
        self.assertEqual(len(ids), 11400)
        self.assertEqual(dict(Counter(r[1] for r in rows[1:])), {
            "KNOWN_OUTAGE_INFORMED": 5928, "TICKET_CREATED": 2052, "ENDED_EARLY": 912, "TRANSFERRED": 798,
            "API_ERROR": 684, "ADDRESS_NOT_UNDERSTOOD": 456, "OUT_OF_SCOPE": 342, "TRANSFER_FAILED": 228})

    def test_committed_predictions_match(self):
        p = os.path.join(ROOT, "predictions_night1.csv")
        if not os.path.exists(p):
            self.skipTest("predictions_night1.csv not generated")
        out = io.StringIO()
        classify.run(os.path.join(DATA, "transcripts.jsonl"), out, lambda m: None)
        with open(p, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read().replace("\r\n", "\n"), out.getvalue())


# ---------------------------------------------------------------- CLI contract

class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "in.jsonl")
        calls = [{"call_id": "c-žľ-1", "events": [GREET, hang(3, "caller")]},
                 {"call_id": "c-2", "events": [GREET, caller(7, "haló"), hang(10, "caller")]}]
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            for c in calls:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, isolated=False):
        cmd = [sys.executable] + (["-I"] if isolated else []) + [os.path.join(ROOT, "classify.py")] + list(args)
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.tmp.name)

    def check_stdout(self, r):
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        text = r.stdout.decode("utf-8")  # strict: must be valid UTF-8
        self.assertNotIn(b"\r\r\n", r.stdout)
        self.assertNotIn("\r\r", text)
        lines = text.replace("\r\n", "\n").split("\n")
        self.assertEqual(lines[0], "call_id,label")
        self.assertEqual(lines[1:], ["c-žľ-1,ENDED_EARLY", "c-2,ENDED_EARLY", ""])
        self.assertIn(b"label distribution", r.stderr)  # summary goes to stderr only
        self.assertNotIn(b"label distribution", r.stdout)

    def test_stdout_without_out(self):
        self.check_stdout(self.run_cli(self.path))

    def test_stdout_isolated_mode(self):
        self.check_stdout(self.run_cli(self.path, isolated=True))

    def test_out_file(self):
        out = os.path.join(self.tmp.name, "pred.csv")
        r = self.run_cli(self.path, "--out", out, isolated=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, b"")
        with open(out, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"\r\r\n", raw)
        self.assertEqual(raw.decode("utf-8").replace("\r\n", "\n"),
                         "call_id,label\nc-žľ-1,ENDED_EARLY\nc-2,ENDED_EARLY\n")

    def test_missing_input_keeps_existing_out_file(self):
        out = os.path.join(self.tmp.name, "pred.csv")
        with open(out, "wb") as f:
            f.write(b"precious,data\n")
        r = self.run_cli(os.path.join(self.tmp.name, "nope.jsonl"), "--out", out)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn(b"Traceback", r.stderr)
        self.assertIn(b"error", r.stderr)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"precious,data\n")

    def test_missing_input_prints_no_lone_header(self):
        r = self.run_cli(os.path.join(self.tmp.name, "nope.jsonl"))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, b"")
        self.assertTrue(r.stderr)

    def test_missing_input_does_not_traceback(self):
        r = self.run_cli(os.path.join(self.tmp.name, "nope.jsonl"))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn(b"Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
