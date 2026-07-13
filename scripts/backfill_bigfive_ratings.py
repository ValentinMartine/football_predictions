"""Backfill historical Big Five player/team computed ratings from Understat.

Understat player-match data is available reliably from the 2014 season onward.
This script builds a season-indexed store used by the website for historical
player ratings and computed XI strength.

Usage examples:
  python scripts/backfill_bigfive_ratings.py
  python scripts/backfill_bigfive_ratings.py --from-season 2018 --to-season 2025
  python scripts/backfill_bigfive_ratings.py --league "ENG-Premier League"
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import soccerdata as sd

from build_lineups import LEAGUES, POS_GROUP, player_note

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "computed_ratings_history.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/computed_ratings_history.json")


def season_label(start_year: int) -> str:
    return f"{start_year}-{start_year + 1}"


def _num(value, default=0.0):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    return int(round(_num(value, default)))


def load_existing() -> dict:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {
        "source": "Understat via soccerdata",
        "note": "Historical Big Five player-match aggregates. Understat player data is reliable from 2014 onward; 2000-2013 remain match/team-history only.",
        "generated_at": None,
        "season_default": None,
        "leagues": LEAGUES,
        "players": {},
        "teams": {},
        "seasons": {},
        "errors": [],
    }


def save(payload: dict) -> None:
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    blob = json.dumps(payload, ensure_ascii=False, indent=1)
    OUT.write_text(blob, encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(blob, encoding="utf-8")


def aggregate_season(start_year: int, leagues: list[str]) -> tuple[dict, dict, int]:
    us = sd.Understat(leagues=leagues, seasons=season_label(start_year))
    sched = us.read_schedule().reset_index()
    pm = us.read_player_match_stats().reset_index()
    sched = sched[sched.get("has_data", True).astype(bool)] if "has_data" in sched.columns else sched
    score_by_game: dict[int, dict[str, int]] = {}
    for _, row in sched.iterrows():
        gid = row.get("game_id")
        if pd.isna(gid):
            continue
        gid = int(gid)
        home = str(row.get("home_team") or "")
        away = str(row.get("away_team") or "")
        hg = _int(row.get("home_goals"), 0)
        ag = _int(row.get("away_goals"), 0)
        score_by_game[gid] = {home: ag, away: hg}

    players: dict[str, dict] = {}
    teams: dict[str, dict] = {}
    match_count = 0

    for gid, match_df in pm.groupby("game_id"):
        if pd.isna(gid):
            continue
        gid = int(gid)
        match_count += 1
        by_team: dict[str, list[dict]] = {}
        for _, row in match_df.iterrows():
            minutes = _int(row.get("minutes"), 0)
            if minutes <= 0:
                continue
            team = str(row.get("team") or "")
            player = str(row.get("player") or "")
            pos = str(row.get("position") or "")
            conceded = score_by_game.get(gid, {}).get(team)
            if conceded is None:
                # Fallback from player goals if schedule score is missing.
                team_goals = match_df.groupby("team")["goals"].sum().to_dict()
                total = sum(_int(v) for v in team_goals.values())
                conceded = total - _int(team_goals.get(team, 0))
            g = _int(row.get("goals"), 0)
            a = _int(row.get("assists"), 0)
            xg = _num(row.get("xg"), 0.0)
            xa = _num(row.get("xa"), 0.0)
            note = player_note(POS_GROUP.get(pos, "ATT"), g, a, xg, xa, int(conceded), minutes)
            pdata = {
                "player": player,
                "team": team,
                "league": str(row.get("league") or ""),
                "pos": pos,
                "note": note,
                "mins": minutes,
                "g": g,
                "a": a,
                "xg": xg,
                "xa": xa,
                "shots": _int(row.get("shots"), 0),
                "kp": _int(row.get("key_passes"), 0),
                "yc": _int(row.get("yellow_cards"), 0),
                "rc": _int(row.get("red_cards"), 0),
            }
            by_team.setdefault(team, []).append(pdata)
            key = f"{player}|{team}"
            agg = players.setdefault(key, {
                "player": player,
                "team": team,
                "league": pdata["league"],
                "pos_counts": {},
                "note_sum": 0.0,
                "matches": 0,
                "mins": 0,
                "g": 0,
                "a": 0,
                "xg": 0.0,
                "xa": 0.0,
                "shots": 0,
                "kp": 0,
                "yc": 0,
                "rc": 0,
            })
            agg["pos_counts"][pos] = agg["pos_counts"].get(pos, 0) + 1
            agg["note_sum"] += note
            agg["matches"] += 1
            agg["mins"] += minutes
            agg["g"] += g
            agg["a"] += a
            agg["xg"] += xg
            agg["xa"] += xa
            agg["shots"] += pdata["shots"]
            agg["kp"] += pdata["kp"]
            agg["yc"] += pdata["yc"]
            agg["rc"] += pdata["rc"]

        for team, plist in by_team.items():
            notes = [p["note"] for p in plist]
            if not notes:
                continue
            league = plist[0].get("league") or ""
            tagg = teams.setdefault(team, {"team": team, "league": league, "power_sum": 0.0, "matches": 0})
            tagg["power_sum"] += sum(notes) * (11.0 / len(notes))
            tagg["matches"] += 1

    out_players = {}
    for key, p in players.items():
        matches = p["matches"]
        if matches <= 0:
            continue
        pos = max(p["pos_counts"].items(), key=lambda item: item[1])[0] if p["pos_counts"] else None
        out_players[key] = {
            "player": p["player"],
            "team": p["team"],
            "league": p["league"],
            "pos": pos,
            "note": round(p["note_sum"] / matches, 2),
            "matches": matches,
            "mins": p["mins"],
            "g": p["g"],
            "a": p["a"],
            "xg": round(p["xg"], 1),
            "xa": round(p["xa"], 1),
            "shots": p["shots"],
            "kp": p["kp"],
            "yc": p["yc"],
            "rc": p["rc"],
        }
    out_teams = {
        team: {
            "team": row["team"],
            "league": row["league"],
            "power": round(row["power_sum"] / row["matches"], 1),
            "matches": row["matches"],
        }
        for team, row in teams.items()
        if row["matches"] > 0
    }
    return out_players, out_teams, match_count


def aggregate_season_resilient(start_year: int, leagues: list[str], errors: list[dict], label: str) -> tuple[dict, dict, int]:
    """Aggregate a season, falling back league-by-league if soccerdata breaks on one league."""
    try:
        return aggregate_season(start_year, leagues)
    except Exception as exc:  # noqa: BLE001
        if len(leagues) <= 1:
            raise
        print(f"{label}: full-season aggregate failed ({exc}); retrying league by league", flush=True)
    all_players: dict[str, dict] = {}
    all_teams: dict[str, dict] = {}
    total_matches = 0
    for league in leagues:
        try:
            players, teams, matches = aggregate_season(start_year, [league])
            all_players.update(players)
            all_teams.update(teams)
            total_matches += matches
            print(f"  {label} {league}: ok ({len(players)} players, {len(teams)} teams)", flush=True)
        except Exception as exc:  # noqa: BLE001
            errors.append({"season": label, "league": league, "error": str(exc)})
            print(f"  {label} {league}: failed ({exc})", flush=True)
    if not all_players:
        raise RuntimeError(f"No player data recovered for {label}")
    return all_players, all_teams, total_matches
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-season", type=int, default=2014)
    parser.add_argument("--to-season", type=int, default=2025)
    parser.add_argument("--league", action="append", choices=LEAGUES, help="Restrict to one or more soccerdata league names.")
    parser.add_argument("--force", action="store_true", help="Recompute seasons already present.")
    args = parser.parse_args()

    leagues = args.league or LEAGUES
    payload = load_existing()
    payload["leagues"] = leagues
    payload.setdefault("errors", [])

    for year in range(args.from_season, args.to_season + 1):
        label = season_label(year)
        if not args.force and label in payload.get("seasons", {}):
            print(f"{label}: already present, skipped", flush=True)
            continue
        try:
            payload["errors"] = [e for e in payload.get("errors", []) if e.get("season") != label]
            players, teams, matches = aggregate_season_resilient(year, leagues, payload["errors"], label)
            payload.setdefault("seasons", {})[label] = {
                "players": len(players),
                "teams": len(teams),
                "matches": matches,
            }
            # Replace flattened rows for this season.
            payload["players"] = {k: v for k, v in payload.get("players", {}).items() if not k.endswith(f"|{label}")}
            payload["teams"] = {k: v for k, v in payload.get("teams", {}).items() if not k.endswith(f"|{label}")}
            for key, value in players.items():
                payload["players"][f"{key}|{label}"] = {**value, "season": label}
            for team, value in teams.items():
                payload["teams"][f"{team}|{label}"] = {**value, "season": label}
            payload["season_default"] = max(payload["seasons"].keys())
            save(payload)
            print(f"{label}: {len(players)} players, {len(teams)} teams, {matches} matches", flush=True)
        except Exception as exc:  # noqa: BLE001
            payload["errors"].append({"season": label, "error": str(exc)})
            save(payload)
            print(f"{label}: failed ({exc})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())