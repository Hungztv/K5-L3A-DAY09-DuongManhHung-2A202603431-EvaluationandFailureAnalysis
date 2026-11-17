"""Regression test for docs/trace_case.md (C-002@11 FM-03) and FM-08 (ReplyLedgerMatch)."""

from __future__ import annotations

import pytest
from pydantic_evals.evaluators import EvaluatorContext

from lab9 import graders
from lab9.trace_case import investigate

pytestmark = pytest.mark.student


def _ctx(trial, label):
    return EvaluatorContext(
        name=trial["result"].get("claim_id", "t"),
        inputs={},
        metadata=None,
        expected_output=label,
        output=trial,
        duration=0.0,
        _span_tree=None,
        attributes={},
        metrics={},
    )


def test_trace_case_c002_seed11_catches_fm03_and_passes_fixed():
    bad = investigate("seeded_regression", "C-002", 11)
    bad_trial, label = bad["trial"], bad["label"]
    assert bad_trial["lab8_pass"] is False
    assert [e["kind"] for e in bad_trial["events"]][2] == "model_override"
    assert graders.DbFactKept().evaluate(_ctx(bad_trial, label)).value is False
    assert graders.RefundAmountCorrect().evaluate(_ctx(bad_trial, label)).value is False

    good = investigate("fixed", "C-002", 11)
    good_trial = good["trial"]
    assert good_trial["lab8_pass"] is True
    assert all(e["kind"] != "model_override" for e in good_trial["events"])
    assert graders.DbFactKept().evaluate(_ctx(good_trial, label)).value is True
    assert graders.RefundAmountCorrect().evaluate(_ctx(good_trial, label)).value is True


def test_fm08_reply_ledger_match_catches_misreport():
    trial = {
        "snapshot": {"refund_vnd": 20000, "refund_count": 1},
        "unexpected_rows": 0,
        "blob": "",
        "events": [{"kind": "reply", "payload": {"text": "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."}}],
        "result": {"proposal_amount": 35000},
        "lab8_pass": True,
        "lab8_reason": None,
    }
    res = graders.ReplyLedgerMatch().evaluate(_ctx(trial, {"refund_vnd": 20000}))
    assert res.value is False
    assert "35000" in (res.reason or "")

    clean_trial = {
        **trial,
        "events": [{"kind": "reply", "payload": {"text": "Dạ, LogiX đã hoàn 20.000đ cho đơn O-808."}}],
    }
    assert graders.ReplyLedgerMatch().evaluate(_ctx(clean_trial, {"refund_vnd": 20000})).value is True
