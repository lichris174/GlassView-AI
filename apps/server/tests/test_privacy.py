"""Redaction tests: secrets/PII are masked, labels survive, ordinary text and
invalid card numbers are left intact."""

from __future__ import annotations

from glassview_ai.privacy import redact, scan


def test_redacts_common_pii() -> None:
    text = "Mail me at jane.doe@example.com or call 415-555-0132. SSN 123-45-6789."
    clean, findings = redact(text)
    assert "jane.doe@example.com" not in clean
    assert "[REDACTED:EMAIL]" in clean
    assert "[REDACTED:PHONE]" in clean
    assert "[REDACTED:SSN]" in clean
    kinds = {f.kind for f in findings}
    assert {"EMAIL", "PHONE", "SSN"} <= kinds


def test_redacts_tokens_and_keys() -> None:
    text = (
        "AWS key AKIAIOSFODNN7EXAMPLE and "
        "token: ghp_1234567890abcdefghijklmnopqrstuvwxyz12"
    )
    clean, findings = redact(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in clean
    assert "ghp_" not in clean
    assert {"AWS_ACCESS_KEY", "GITHUB_TOKEN"} <= {f.kind for f in findings}


def test_secret_assignment_keeps_label_masks_value() -> None:
    clean, findings = redact('password = "hunter2supersecret"')
    assert "hunter2supersecret" not in clean
    assert "password" in clean  # the label stays so context is readable
    assert "[REDACTED:SECRET]" in clean
    assert any(f.kind == "SECRET" for f in findings)


def test_valid_card_redacted_invalid_left_alone() -> None:
    valid = "card 4111 1111 1111 1111 on file"  # passes Luhn
    invalid = "order id 1234 5678 9012 3456 shipped"  # fails Luhn
    clean_v, fv = redact(valid)
    clean_i, fi = redact(invalid)
    assert "[REDACTED:CREDIT_CARD]" in clean_v
    assert any(f.kind == "CREDIT_CARD" for f in fv)
    assert "1234 5678 9012 3456" in clean_i
    assert not any(f.kind == "CREDIT_CARD" for f in fi)


def test_clean_text_unchanged() -> None:
    text = "The build failed because the import path was wrong on line 42."
    clean, findings = redact(text)
    assert clean == text
    assert findings == []


def test_scan_does_not_mutate() -> None:
    text = "reach me at a@b.co"
    found = scan(text)
    assert found and found[0].kind == "EMAIL"
