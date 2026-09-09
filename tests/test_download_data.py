from datetime import date

from scripts.download_data import (
    canonical_team_name,
    current_season_start_year,
    football_data_org_rows,
    result_code,
    season_code,
    seasons_to_fetch,
)


def test_current_season_switches_in_july() -> None:
    assert current_season_start_year(date(2026, 6, 30)) == 2025
    assert current_season_start_year(date(2026, 7, 1)) == 2026


def test_season_code_uses_two_digit_football_data_format() -> None:
    assert season_code(2025) == "2526"
    assert season_code(2026) == "2627"


def test_seasons_to_fetch_includes_active_season() -> None:
    assert seasons_to_fetch(first_start_year=2024, today=date(2026, 9, 9)) == ["2425", "2526", "2627"]


def test_result_code_matches_football_data_format() -> None:
    assert result_code(2, 1) == "H"
    assert result_code(1, 1) == "D"
    assert result_code(0, 1) == "A"


def test_canonical_team_name_maps_football_data_org_aliases() -> None:
    assert canonical_team_name({"name": "Manchester City FC"}) == "Man City"
    assert canonical_team_name({"name": "FC Bayern München"}) == "Bayern Munich"


def test_football_data_org_rows_keep_finished_matches_only() -> None:
    payload = {
        "matches": [
            {
                "status": "FINISHED",
                "utcDate": "2026-08-15T14:00:00Z",
                "homeTeam": {"name": "Manchester City FC"},
                "awayTeam": {"shortName": "Arsenal"},
                "score": {"fullTime": {"home": 2, "away": 0}},
            },
            {
                "status": "SCHEDULED",
                "utcDate": "2026-08-16T14:00:00Z",
                "homeTeam": {"name": "Chelsea FC"},
                "awayTeam": {"name": "Liverpool FC"},
                "score": {"fullTime": {"home": None, "away": None}},
            },
        ]
    }

    rows = football_data_org_rows(payload, "E0")

    assert len(rows) == 1
    assert rows[0]["Div"] == "E0"
    assert rows[0]["Date"] == "15/08/2026"
    assert rows[0]["HomeTeam"] == "Man City"
    assert rows[0]["AwayTeam"] == "Arsenal"
    assert rows[0]["FTR"] == "H"
