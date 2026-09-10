"""Validators: what gets auto-approved vs held for review."""
from __future__ import annotations

import db
from validators import classify


def test_clean_change_is_approved():
    status, note = classify("Grocery", 105.0, 100.0)
    assert status == db.STATUS_APPROVED
    assert note == ""


def test_suspicious_jump_is_held_for_review():
    # +25% on a grocery staple: too big to trust blindly
    status, note = classify("Grocery", 125.0, 100.0)
    assert status == db.STATUS_PENDING
    assert "suspicious" in note


def test_fresh_produce_allows_bigger_swings():
    status, _ = classify("Fresh produce", 140.0, 100.0)
    assert status == db.STATUS_APPROVED


def test_suspicious_drop_is_held_for_review():
    status, note = classify("Energy", 60.0, 100.0)
    assert status == db.STATUS_PENDING
    assert "suspicious" in note


def test_non_positive_price_is_rejected():
    status, note = classify("Grocery", 0, 100.0)
    assert status == db.STATUS_REJECTED
    status, _ = classify("Grocery", -5, 100.0)
    assert status == db.STATUS_REJECTED


def test_no_baseline_is_approved():
    status, _ = classify("Grocery", 100.0, None)
    assert status == db.STATUS_APPROVED