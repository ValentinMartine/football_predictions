# Football clubs predictions

Predictions for the Premier League, La Liga, Serie A, Bundesliga and Ligue 1.

Data comes from football-data.co.uk CSV files: match results, match statistics and real bookmaker odds.

## Run

```bash
pip install -r requirements.txt
python scripts/download_data.py
python scripts/train_and_backtest.py
python -m src.export
```

## Method

- Chronological feature pipeline without leakage.
- Club Elo baseline with home advantage and margin-of-victory update.
- Rolling form, goals, shots, shots on target and rest features.
- LightGBM 3-class model for home/draw/away.
- Blend ML + Elo tuned on temporal validation.
- Selective betting backtest on real closing odds with fractional Kelly.

## Data

- Source: https://www.football-data.co.uk/
- Leagues: E0, SP1, I1, D1, F1.
- Seasons: 2015-2016 to 2025-2026.
