from datetime import date

from scripts.download_data import current_season_start_year, season_code, seasons_to_fetch


def test_current_season_switches_in_july() -> None:
    assert current_season_start_year(date(2026, 6, 30)) == 2025
    assert current_season_start_year(date(2026, 7, 1)) == 2026


def test_season_code_uses_two_digit_football_data_format() -> None:
    assert season_code(2025) == "2526"
    assert season_code(2026) == "2627"


def test_seasons_to_fetch_includes_active_season() -> None:
    assert seasons_to_fetch(first_start_year=2024, today=date(2026, 9, 9)) == ["2425", "2526", "2627"]
