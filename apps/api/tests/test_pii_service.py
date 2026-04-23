"""Tests for expanded PII regex library in ``app.services.pii_service``."""
from __future__ import annotations

from app.services.pii_service import strip_pii, strip_pii_with_meta


def _has_cat(text: str, cats: list[str], name: str) -> bool:
    return name in cats


class TestBackwardsCompat:
    def test_none_passthrough(self):
        assert strip_pii(None) is None

    def test_empty_passthrough(self):
        assert strip_pii("") == ""

    def test_plain_text_unchanged(self):
        assert strip_pii("I learned a lot in the course.") == "I learned a lot in the course."


class TestSSN:
    def test_ssn_with_hyphen(self):
        r = strip_pii_with_meta("My SSN is 123-45-6789.")
        assert "***" in r.text
        assert "123-45-6789" not in r.text
        assert "ssn" in r.categories

    def test_ssn_with_spaces(self):
        r = strip_pii_with_meta("ssn 123 45 6789")
        assert "***" in r.text
        assert "ssn" in r.categories

    def test_ssn_no_separator_with_context(self):
        r = strip_pii_with_meta("Social security: 123456789")
        assert "***" in r.text
        assert "ssn" in r.categories

    def test_nine_digits_without_context_not_redacted(self):
        # Should NOT redact — random 9-digit sequence without SSN cue.
        r = strip_pii_with_meta("My order number was 123456789 for reference.")
        assert "123456789" in r.text
        assert "ssn" not in r.categories


class TestEmail:
    def test_email(self):
        r = strip_pii_with_meta("Reach me at jane.doe@example.com today.")
        assert "***" in r.text
        assert "jane.doe@example.com" not in r.text
        assert "email" in r.categories


class TestPhone:
    def test_us_phone_parens(self):
        r = strip_pii_with_meta("Call (555) 123-4567 anytime.")
        assert "***" in r.text
        assert "phone" in r.categories

    def test_us_phone_dashes(self):
        r = strip_pii_with_meta("Call 555-123-4567 anytime.")
        assert "***" in r.text
        assert "phone" in r.categories

    def test_us_phone_with_country(self):
        r = strip_pii_with_meta("+1 555 123 4567")
        assert "***" in r.text
        assert "phone" in r.categories

    def test_intl_phone(self):
        r = strip_pii_with_meta("UK office: +44 20 7946 0958")
        assert "***" in r.text
        assert "phone" in r.categories


class TestCreditCard:
    def test_valid_luhn_redacted(self):
        # 4111 1111 1111 1111 is a standard Visa Luhn-valid test number.
        r = strip_pii_with_meta("Card: 4111 1111 1111 1111")
        assert "***" in r.text
        assert "credit_card" in r.categories
        assert "4111 1111 1111 1111" not in r.text

    def test_invalid_luhn_not_redacted(self):
        # 1234 5678 9012 3456 is not Luhn-valid.
        r = strip_pii_with_meta("Ref: 1234 5678 9012 3456")
        assert "credit_card" not in r.categories


class TestAddress:
    def test_street_address_with_suffix(self):
        r = strip_pii_with_meta("I live at 123 Main Street in Boston.")
        assert "***" in r.text
        assert "address" in r.categories

    def test_avenue_abbrev(self):
        r = strip_pii_with_meta("Come by 456 Oak Ave.")
        assert "***" in r.text
        assert "address" in r.categories

    def test_zip_near_address_redacted(self):
        r = strip_pii_with_meta("Mail it to 123 Pine St, Boston MA 02108.")
        assert "***" in r.text
        assert "zip" in r.categories or "address" in r.categories

    def test_standalone_5digits_not_zip(self):
        r = strip_pii_with_meta("We trained 12345 participants last year.")
        assert "zip" not in r.categories


class TestDOB:
    def test_dob_numeric(self):
        r = strip_pii_with_meta("DOB: 01/23/1985")
        assert "***" in r.text
        assert "dob" in r.categories

    def test_dob_spelled(self):
        r = strip_pii_with_meta("Date of birth: January 23, 1985")
        assert "***" in r.text
        assert "dob" in r.categories

    def test_born_on(self):
        r = strip_pii_with_meta("I was born on 3/5/1992.")
        assert "***" in r.text
        assert "dob" in r.categories


class TestDriverLicense:
    def test_dl_with_label(self):
        r = strip_pii_with_meta("DL: CA12345678")
        assert "***" in r.text
        assert "license" in r.categories


class TestIP:
    def test_ipv4(self):
        r = strip_pii_with_meta("Server at 192.168.1.100 went down.")
        assert "***" in r.text
        assert "ip" in r.categories


class TestMultiple:
    def test_multiple_categories(self):
        r = strip_pii_with_meta(
            "Email me at jane@x.com or call 555-123-4567. My SSN is 123-45-6789."
        )
        assert r.count >= 3
        assert "email" in r.categories
        assert "phone" in r.categories
        assert "ssn" in r.categories

    def test_count_increments(self):
        r = strip_pii_with_meta("Call 555-123-4567 or 555-999-8888.")
        assert r.count >= 2
