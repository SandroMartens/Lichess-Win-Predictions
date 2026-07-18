# %%
import io
import sqlite3

import chess
import chess.engine
import chess.pgn
from tqdm import tqdm


# %%
def create_dataframe(
    n_games: int, file_path: str
) -> list[tuple[str, str, int, int, int]]:
    """Extract the following features from each game in the pgn file:
        URL of the game,
        PGN of the game,
        The result

    Return a list of tuples.
    """
    games = []
    with open(file_path) as pgn_file:
        for _ in range(n_games):
            exporter = chess.pgn.StringExporter(headers=False)
            game = chess.pgn.read_game(pgn_file)
            if game is not None:
                url = game.headers["LichessURL"]
                pgn = game.accept(exporter)
                termination = game.headers["Termination"]
                elo_white = game.headers["WhiteElo"]
                elo_black = game.headers["BlackElo"]
                if game.headers["Result"] == "1-0":
                    result = 1
                elif game.headers["Result"] == "0-1":
                    result = -1
                else:
                    result = 0
            else:
                break

            if termination == "Normal":
                games.append((url, pgn, result, elo_white, elo_black))

    return games


# %%
def write_games(games: list[tuple], db_path: str) -> None:
    """Create a SQL Database with one table games, which has columns
    URL and PGN.
    """

    with sqlite3.connect(db_path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS
                games(
                    url TEXT ,
                    pgn TEXT,
                    result INTEGER,
                    elo_white INTEGER,
                    elo_black INTEGER,
                    UNIQUE (url)
                )
            """
        )

        con.executemany(
            """
            INSERT OR IGNORE INTO
                games(url, pgn, result, elo_white, elo_black)
            VALUES
                (:url, :pgn, :result, :elo_white, :elo_black)
            """,
            games,
        )
    con.close()


# %%
def extract_positions(pgn: str) -> list[tuple[int, str]]:
    """Take a pgn and return a list of positions (fen) and ply numbers."""

    game = chess.pgn.read_game(io.StringIO(pgn))
    positions = []
    if game is not None:
        main_line = list(game.mainline())
        for move in main_line:
            board = move.board()
            positions.append((board.ply(), board.fen()))

        return positions
    else:
        raise RuntimeError


# %%
def write_positions(db_path: str) -> None:
    """Read the pgn from the games table and write the fen and ply of each
    move in a new table positions
    """

    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS
                positions(
                    game_id INTEGER,
                    ply  INTEGER NOT NULL,
                    fen TEXT,
                    eval REAL,
                    UNIQUE (game_id, ply)
                )
            """
        )
        # ponytail: naive add-column-if-missing, needed since games.sqlite
        # predates these columns. Swap for a real migration if schema churns.
        for column in ("win_chance", "lose_chance", "draw_chance"):
            try:
                con.execute(f"ALTER TABLE positions ADD COLUMN {column} FLOAT")
            except sqlite3.OperationalError:
                pass

        cur.execute(
            """
            SELECT rowid as game_id, pgn
            FROM games
            WHERE game_id NOT IN (
                SELECT game_id
                FROM positions
            )
            """
        )
        for game_id, pgn in cur:
            positions = extract_positions(pgn)
            positions = [(game_id, fen, ply) for ply, fen in positions]
            con.executemany(
                """
                INSERT OR IGNORE INTO
                    positions(game_id, fen, ply)
                VALUES
                    (:game_id, :fen, :ply)
                """,
                (positions),
            )

    cur.close()
    con.close()


# %%
def annotate_positions(
    engine_path: str,
    db_path: str,
    engine_options: dict,
    limit: chess.engine.Limit,
) -> None:
    """Read all positions and run them through the given UCI engine. Write
    the eval and WDL chances back to the db.
    """

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        res = con.execute(
            """
            SELECT
                rowid as position_id, fen
            FROM positions
            WHERE eval IS NULL
            """
        )

        with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
            engine.configure({**engine_options, "UCI_ShowWDL": True})
            for i, row in enumerate(tqdm(res, unit="positions")):
                board = chess.Board(fen=row["fen"])
                if board.is_checkmate():
                    continue
                evaluation = engine.analyse(board, limit)
                cp = evaluation["score"].white().score(mate_score=10_000)
                win_chance, draw_chance, lose_chance = evaluation["wdl"].relative
                con.execute(
                    """
                    UPDATE positions
                    SET
                        eval = :eval,
                        win_chance = :win_chance,
                        draw_chance = :draw_chance,
                        lose_chance = :lose_chance
                    WHERE rowid = :position_id
                    """,
                    {
                        "eval": cp,
                        "position_id": row["position_id"],
                        "win_chance": win_chance / 1000,
                        "draw_chance": draw_chance / 1000,
                        "lose_chance": lose_chance / 1000,
                    },
                )
                # Reduce overhead for commits
                if i % 100 == 0:
                    con.commit()
    con.close()


# %%
def main():
    games_path = "..\\lichess_elite_2022-04.pgn"
    stockfish_path = (
        "stockfish-windows-x86-64-avx2\\stockfish\\stockfish-windows-x86-64-avx2.exe"
    )
    lc0_path = "..\\lc0-v0.31.2-windows-gpu-nvidia-cuda\\lc0.exe"
    n_games = 2000

    df = create_dataframe(
        n_games=n_games,
        file_path=games_path,
    )

    write_games(df, db_path="games.sqlite")
    write_positions(db_path="games.sqlite")
    annotate_positions(
        engine_path=stockfish_path,
        db_path="games.sqlite",
        engine_options={"Threads": 12, "Use NNUE": True, "Hash": 3000},
        limit=chess.engine.Limit(nodes=3_000_000),
    )

    write_games(df, db_path="games_leela.sqlite")
    write_positions(db_path="games_leela.sqlite")
    annotate_positions(
        engine_path=lc0_path,
        db_path="games_leela.sqlite",
        engine_options={"Threads": 14},
        limit=chess.engine.Limit(time=0.05),
    )


main()
