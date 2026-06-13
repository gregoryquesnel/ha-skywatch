"""Normalizer functions: pure boundary helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.skywatch.storage.normalizers import (
    coerce_float,
    coerce_int,
    normalize_photo_url,
    parse_iso,
)


class TestNormalizePhotoURL:
    def test_strips_doubled_https_prefix(self) -> None:
        bad = "https:https://cdn.jetphotos.com/200/photo.jpg"
        assert normalize_photo_url(bad) == "https://cdn.jetphotos.com/200/photo.jpg"

    def test_leaves_clean_url_unchanged(self) -> None:
        good = "https://cdn.jetphotos.com/200/photo.jpg"
        assert normalize_photo_url(good) == good

    @pytest.mark.parametrize("falsy", [None, "", 0, False])
    def test_returns_none_for_falsy(self, falsy: object) -> None:
        assert normalize_photo_url(falsy) is None

    def test_returns_none_for_non_string(self) -> None:
        assert normalize_photo_url(42) is None
        assert normalize_photo_url(["url"]) is None


class TestCoerceInt:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (42, 42),
            ("42", 42),
            ("42.5", 42),
            (42.9, 42),
            (-3, -3),
            ("0", 0),
        ],
    )
    def test_valid(self, value: object, expected: int) -> None:
        assert coerce_int(value) == expected

    @pytest.mark.parametrize("value", [None, "", "abc", "12.3.4", [], {}])
    def test_invalid(self, value: object) -> None:
        assert coerce_int(value) is None


class TestCoerceFloat:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (42, 42.0),
            ("3.5", 3.5),
            ("-1.0", -1.0),
            (0, 0.0),
        ],
    )
    def test_valid(self, value: object, expected: float) -> None:
        result = coerce_float(value)
        assert result is not None
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize("value", [None, "", "abc", [], {}])
    def test_invalid(self, value: object) -> None:
        assert coerce_float(value) is None


class TestParseISO:
    def test_aware_iso(self) -> None:
        dt = parse_iso("2026-06-13T20:15:30+00:00")
        assert dt == datetime(2026, 6, 13, 20, 15, 30, tzinfo=UTC)

    def test_zulu_suffix(self) -> None:
        dt = parse_iso("2026-06-13T20:15:30Z")
        assert dt == datetime(2026, 6, 13, 20, 15, 30, tzinfo=UTC)

    def test_naive_treated_as_utc(self) -> None:
        dt = parse_iso("2026-06-13T20:15:30")
        assert dt is not None
        assert dt.tzinfo == UTC

    @pytest.mark.parametrize("value", [None, "", "not a date", "2026-13-99"])
    def test_invalid(self, value: str | None) -> None:
        assert parse_iso(value) is None
