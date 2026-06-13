"""Classifier helpers (helo / military / watch matcher)."""

from __future__ import annotations

import pytest

from custom_components.skywatch.classify import (
    WatchEntry,
    is_helicopter,
    is_military,
    match_watch,
)
from custom_components.skywatch.const import DEFAULT_HELO_CODES, DEFAULT_MILITARY_CODES


class TestIsHelicopter:
    @pytest.mark.parametrize("code", ["H60", "R44", "B212", "EC35", "uh1"])
    def test_known_helos(self, code: str) -> None:
        assert is_helicopter(code, DEFAULT_HELO_CODES) is True

    @pytest.mark.parametrize("code", ["B738", "C17", "A320", "PA31"])
    def test_known_non_helos(self, code: str) -> None:
        assert is_helicopter(code, DEFAULT_HELO_CODES) is False

    @pytest.mark.parametrize("value", [None, "", "  "])
    def test_falsy_inputs(self, value: str | None) -> None:
        assert is_helicopter(value, DEFAULT_HELO_CODES) is False


class TestIsMilitary:
    @pytest.mark.parametrize("code", ["C17", "C130", "P8", "f35", "MQ9"])
    def test_known_military(self, code: str) -> None:
        assert is_military(code, DEFAULT_MILITARY_CODES) is True

    @pytest.mark.parametrize("code", ["B738", "A320", "R44"])
    def test_known_non_military(self, code: str) -> None:
        assert is_military(code, DEFAULT_MILITARY_CODES) is False


class TestWatchEntryFromDict:
    def test_minimal(self) -> None:
        entry = WatchEntry.from_dict({"slug": "abc"})
        assert entry.slug == "abc"
        assert entry.label == "abc"  # fallback to slug

    def test_full(self) -> None:
        entry = WatchEntry.from_dict(
            {
                "slug": "regina_police",
                "label": "Regina Police Air Unit",
                "registration": "C-GRPF",
                "aircraft_code": "C182",
                "match_blocked": True,
            }
        )
        assert entry.slug == "regina_police"
        assert entry.label == "Regina Police Air Unit"
        assert entry.registration == "C-GRPF"
        assert entry.aircraft_code == "C182"
        assert entry.match_blocked is True

    def test_missing_slug_raises(self) -> None:
        with pytest.raises(ValueError):
            WatchEntry.from_dict({"label": "x"})


class TestMatchWatch:
    @pytest.fixture
    def watch_list(self) -> tuple[WatchEntry, ...]:
        return (
            WatchEntry(slug="regina_police", label="RPS", aircraft_code="C182", match_blocked=True),
            WatchEntry(slug="my_cessna", label="My Cessna", registration="C-FAAA"),
            WatchEntry(slug="neighbour", label="Neighbour", registration="N12345"),
        )

    def test_registration_match(self, watch_list: tuple[WatchEntry, ...]) -> None:
        result = match_watch(
            {"aircraft_registration": "C-FAAA", "aircraft_code": "C172"},
            watch_list,
        )
        assert result is not None
        assert result.slug == "my_cessna"

    def test_registration_match_case_insensitive(self, watch_list: tuple[WatchEntry, ...]) -> None:
        result = match_watch(
            {"aircraft_registration": "c-faaa", "aircraft_code": "C172"},
            watch_list,
        )
        assert result is not None
        assert result.slug == "my_cessna"

    def test_blocked_fingerprint_match(self, watch_list: tuple[WatchEntry, ...]) -> None:
        result = match_watch(
            {
                "aircraft_registration": None,
                "aircraft_code": "C182",
                "callsign": "Blocked",
            },
            watch_list,
        )
        assert result is not None
        assert result.slug == "regina_police"

    def test_blocked_fingerprint_misses_if_callsign_not_blocked(
        self, watch_list: tuple[WatchEntry, ...]
    ) -> None:
        # Same aircraft_code, but callsign isn't 'Blocked' — not a match.
        result = match_watch(
            {
                "aircraft_registration": None,
                "aircraft_code": "C182",
                "callsign": "ACA123",
            },
            watch_list,
        )
        assert result is None

    def test_blocked_fingerprint_misses_if_registration_present(
        self, watch_list: tuple[WatchEntry, ...]
    ) -> None:
        # Registration is visible — that's not the C-GRPF pattern.
        result = match_watch(
            {
                "aircraft_registration": "C-FXYZ",
                "aircraft_code": "C182",
                "callsign": "Blocked",
            },
            watch_list,
        )
        assert result is None

    def test_no_match_returns_none(self, watch_list: tuple[WatchEntry, ...]) -> None:
        result = match_watch(
            {"aircraft_registration": "N99999", "aircraft_code": "C172"},
            watch_list,
        )
        assert result is None

    def test_empty_watch_list_returns_none(self) -> None:
        result = match_watch({"aircraft_registration": "C-FAAA"}, ())
        assert result is None
