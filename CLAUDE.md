# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A data-analysis project that reproduces the Lichess win-probability formula (centipawn eval → win chance) by fitting a logistic regression on real games. Background and results: [readme.md](readme.md), which reproduces [Lichess' accuracy page](https://lichess.org/page/accuracy).

## Two-stage pipeline

The work splits into a data-building script and analysis notebooks, connected only by the sqlite files.

1. **[create_database.py](create_database.py)** — builds both databases. Runs `main()` at import time (module-level call on the last line), so *importing this file executes the whole pipeline*. `main()` runs the same three stages twice, once per engine:
   - `games.sqlite`: Stockfish, `Limit(nodes=3_000_000)`, options `Threads: 12, Use NNUE: True, Hash: 3000`
   - `games_leela.sqlite`: lc0, `Limit(time=0.05)`, options `Threads: 14`
   The stages (each idempotent and resumable, parametrized by `db_path`):
   - `create_dataframe` + `write_games`: parse a Lichess PGN into the `games` table. Keeps only `Termination == "Normal"`. Result encoding: `1-0`→`1`, `0-1`→`-1`, draw→`0`.
   - `write_positions`: expand each game's PGN into one row per ply (fen + ply) in `positions`. Skips games already in `positions`. Contains an add-column-if-missing loop for the WDL columns (marked `ponytail:`) because `games.sqlite` predates them.
   - `annotate_positions`: run each position through the given UCI engine (checkmate positions skipped), writing centipawn `eval` (mate scored as ±10000) and WDL chances. Only touches rows `WHERE eval IS NULL`, commits every 100 — a killed run resumes where it stopped.

2. **[win_prob.ipynb](win_prob.ipynb)** — loads from `games.sqlite`, fits the model, saves plots to `images/upload/`. Notable steps:
   - Deduplicates positions by `fen` and weights each move so every *game* contributes equally to the fit (`weight = 1 / moves_in_game`), regardless of length.
   - sklearn `Pipeline` of `StandardScaler` → `LogisticRegressionCV` (l2, `Cs=20`). The single active feature is `eval`; `ply`, `elo_dif`, `increment`, `start_time` are wired up but commented out in the `features` list.
   - Do NOT enable `class_weight="balanced"`: CV then picks the grid-edge regularization (`C=0.0001`) and the coefficient collapses (~0.0002 instead of ~0.0024) — accuracy stays ~0.70 but calibration, the whole point of the analysis, is destroyed.
   - The fitted coefficient (the exponent the readme discusses) is recovered as `classifier.coef_ / scaler.scale_`, since the model trains on standardized inputs.
   - Draws are dropped for the fit (`WHERE g.result != 0`); result is remapped to `0`/`2` for the two classes.

Side experiment: **[new.ipynb](new.ipynb)** — fits the win-probability curve non-parametrically (per-outcome eval histograms → `scipy.stats.rv_histogram` CDFs → `curve_fit` against the Lichess sigmoid) instead of via logistic regression. Exploratory, no writeup.

## DB schema (`games.sqlite`, `games_leela.sqlite`)

- `games(url, pgn, result, elo_white, elo_black, UNIQUE(url))` — `games.sqlite` additionally has `increment`, `start_time` (written by code that was never committed; treat as data-only columns).
- `positions(game_id, ply, fen, eval, win_chance, lose_chance, draw_chance, UNIQUE(game_id, ply))` — `game_id` = `games.rowid`.
- `games.sqlite`: ~1500 Stockfish-annotated games (no WDL values). `games_leela.sqlite`: ~740 lc0-annotated games incl. WDL.

## Running

Requires Python 3.14 (`.python-version`). Uses `uv`; dependencies are declared in `pyproject.toml`/`uv.lock` (incl. `ipykernel` for notebooks).

- Setup: `uv sync`
- Data build: `uv run create_database.py`
- Analysis: open `win_prob.ipynb` in Jupyter / VS Code (kernel: `.venv`).

**External inputs are hardcoded in `main()` and not in the repo:** the source PGN (`../lichess_elite_2022-04.pgn`, from the [Lichess Elite Database](https://database.nikonoel.fr/); its games must carry a `LichessURL` header) and the two engine binaries (`stockfish_path`, `lc0_path`). Fix these paths for the local machine before running.

There are no tests, linters, or build steps.
