"""The moderation log lines must not carry an email address (SU11A-32).

journald keeps scrp-api output for up to 30 days, longer than an account
deletion is allowed to leave the address around. The moderation EMAIL to
info@xxl.co.il still names the author; only the log line is checked here.
No database, no SMTP: the item lookup and send_email are replaced.
    python -m pytest tests/test_moderation_logging.py -q
"""
import logging

import pytest

import api.routers.ratings as R

AUTHOR = "author.private@example.test"
REPORTER = "reporter.private@example.test"


@pytest.fixture
def sent(monkeypatch):
    mails = []
    monkeypatch.setattr(R, "_item_name", lambda rating_id: "test item")
    monkeypatch.setattr(R, "send_email", lambda **kw: mails.append(kw) or True)
    return mails


def test_auto_hide_log_has_rating_id_and_no_email(sent, caplog):
    caplog.set_level(logging.DEBUG)
    R._notify_moderation(rating_id=4242, item_code="7290000000001",
                         user_email=AUTHOR, term="badword", rating=1, comment="x")
    assert "rating_id=4242" in caplog.text
    assert AUTHOR not in caplog.text and "@" not in caplog.text
    # The mail itself is unchanged and still names the author.
    assert AUTHOR in sent[0]["body_text"]


def test_user_report_log_has_rating_id_and_no_email(sent, caplog):
    caplog.set_level(logging.DEBUG)
    R._notify_report(rating_id=4343, item_code="7290000000002",
                     reporter_email=REPORTER, reason="spam")
    assert "rating_id=4343" in caplog.text
    assert REPORTER not in caplog.text and "@" not in caplog.text
    assert REPORTER in sent[0]["body_text"]
