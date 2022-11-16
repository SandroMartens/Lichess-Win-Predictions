# %%
import io
import sqlite3

import chess
import chess.engine
import chess.pgn
from tqdm import tqdm


# %%
def dict_factory(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict:
    """Defines how to return a SQL row."""

    col_names = [col[0] for col in cursor.description]
    return dict(zip(col_names, row))


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
def write_games(games: list[tuple]) -> None:
    """Create a SQL Database with one table games, which has columns
    URL and PGN.
    """

    with sqlite3.connect("games.sqlite") as con:
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
def write_positions() -> None:
    """Read the pgn from the games table and write the fen and ply of each
    move in a new table positions
    """

    with sqlite3.connect("games.sqlite") as con:
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
def annotate_positions(engine_path: str) -> None:
    """Read all positions and run them through stockfish. Write the results
    back to the db.
    """

    with sqlite3.connect("games.sqlite") as con:
        con.row_factory = dict_factory
        res = con.execute(
            """
            SELECT
                rowid as position_id, fen
            FROM positions
            WHERE eval IS NULL
            """
        )

        with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
            engine.configure({"Threads": 14, "Use NNUE": True, "Hash": 3000})
            for i, row in enumerate(tqdm(res, unit="positions")):
                board = chess.Board(fen=row["fen"])
                evaluation = engine.analyse(
                    board,
                    chess.engine.Limit(nodes=3_000_000),
                )
                cp = evaluation["score"].white().score(mate_score=10_000)
                con.execute(
                    """
                    UPDATE positions
                    SET eval = :eval
                    WHERE rowid = :position_id
                    """,
                    {"eval": cp, "position_id": row["position_id"]},
                )
                # Reduce overhead for commits
                if i % 100 == 0:
                    con.commit()
    con.close()


# %%
def main():
    games_path = "F:\\Dokumente\\git\\schach\\lichess_elite_2022-04.pgn"
    engine_path = "F:\\Downloads\\stockfish_15_win_x64_avx2\\stockfish_15_x64_avx2.exe"
    n_games = 1050
    df = create_dataframe(
        n_games=n_games,
        file_path=games_path,
    )
    write_games(df)
    write_positions()
    annotate_positions(engine_path=engine_path)


main()
