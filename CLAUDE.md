# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A data-analysis project that reproduces the Lichess win-probability formula (centipawn eval → win chance) by fitting a logistic regression on real games. Background and results: [readme.md](readme.md), which reproduces [Lichess' accuracy page](https://lichess.org/page/accuracy).

## Two-stage pipeline

The work splits into a data-building script and an analysis notebook, connected only by `games.sqlite`.

1. **[create_database.py](create_database.py)** — builds `games.sqlite`. Runs `main()` at import time (module-level call on the last line), so *importing this file executes the whole pipeline*. Three stages, each idempotent and resumable:
   - `create_dataframe` + `write_games`: parse a Lichess PGN into the `games` table. Keeps only `Termination == "Normal"`. Result encoding: `1-0`→`1`, `0-1`→`-1`, draw→`0`.
   - `write_positions`: expand each game's PGN into one row per ply (fen + ply) in `positions`. Skips games already in `positions` (`WHERE game_id NOT IN (...)`).
   - `annotate_positions`: run each position through a UCI engine, writing centipawn `eval` (mate scored as ±10000) and per-position WDL chances. Only touches rows `WHERE eval IS NULL`, commits every 100 — so a killed run resumes where it stopped.

2. **[win_prob.ipynb](win_prob.ipynb)** — loads from sqlite, fits the model, plots. Notable steps:
   - Deduplicates positions by `fen` and weights each move so every *game* contributes equally to the fit (`weight = 1 / moves_in_game`), regardless of length.
   - sklearn `Pipeline` of `StandardScaler` → `LogisticRegressionCV`. The single active feature is `eval`; `ply` and `elo_dif` are wired up but commented out in the `features` list. A `UMAP` embedder step is also present but commented out.
   - The fitted coefficient (the exponent the readme discusses) is recovered as `classifier.coef_ / scaler.scale_`, since the model trains on standardized inputs.
   - Draws are dropped for the fit (`WHERE g.result != 0`); result is remapped to `0`/`2` for the two classes.

## DB schema (`games.sqlite`)

- `games(url, pgn, result, elo_white, elo_black, UNIQUE(url))`
- `positions(game_id, ply, fen, eval, win_chance, lose_chance, draw_chance, UNIQUE(game_id, ply))` — `game_id` = `games.rowid`.

## Running

Requires Python 3.14 (`.python-version`, `pyproject.toml`). Uses `uv`.

**Dependencies are not declared** — `pyproject.toml` `dependencies` and `uv.lock` are both empty, and `.venv` has no packages installed. Before anything runs you must add the actual imports:

```
uv add python-chess tqdm scikit-learn pandas numpy matplotlib seaborn umap-learn
```

Then:
- Data build: `uv run create_database.py`
- Analysis: open `win_prob.ipynb` in Jupyter / VS Code.

**External inputs are hardcoded in `main()` and not in the repo:** the source PGN (`../lichess_elite_2022-04.pgn`, from the [Lichess Elite Database](https://database.nikonoel.fr/); its games must carry a `LichessURL` header) and the engine binary. `main()` currently passes `lc0_path` to `annotate_positions`; a `stockfish_path` is also defined. Fix these paths for the local machine before running. Engine config is in `annotate_positions`: `Threads: 14`, `UCI_ShowWDL: True`, `Limit(time=0.05)`.

There are no tests, linters, or build steps.
