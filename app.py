from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import random
import string

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DB = "database.db"

# ------------------ DB ------------------
def get_db():
    return sqlite3.connect(DB)

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_code TEXT UNIQUE,
            player1_secret TEXT,
            player2_secret TEXT,
            player1_ready INTEGER DEFAULT 0,
            player2_ready INTEGER DEFAULT 0,
            turn INTEGER DEFAULT 1,
            winner TEXT
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS guesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            player TEXT,
            guess TEXT,
            x INTEGER,
            y INTEGER
        )""")

init_db()

# ------------------ HELPERS ------------------
def valid_number(n):
    return n and len(n) == 4 and all(d in "123456789" for d in n) and len(set(n)) == 4

def feedback(secret, guess):
    x = sum(d in secret for d in guess)
    y = sum(secret[i] == guess[i] for i in range(4))
    return x, y

def code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

# ------------------ ROUTES ------------------
@app.route("/")
def home():
    session.clear()
    return render_template("home.html")

# ---------- CREATE ----------
@app.route("/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        game_code = code()

        with get_db() as conn:
            conn.execute("INSERT INTO games (game_code) VALUES (?)", (game_code,))

        session["player"] = "Player 1"
        session["game_code"] = game_code
        return redirect(url_for("wait", game_code=game_code))

    return redirect(url_for("home"))

# ---------- JOIN ----------
@app.route("/join", methods=["GET", "POST"])
def join():
    if request.method == "POST":
        game_code = request.form["game_code"].upper()

        with get_db() as conn:
            game = conn.execute(
                "SELECT * FROM games WHERE game_code=?", (game_code,)
            ).fetchone()

        if not game:
            return render_template("join_game.html", error="Invalid room code")

        session["player"] = "Player 2"
        session["game_code"] = game_code
        return redirect(url_for("secret", game_code=game_code))

    return render_template("join_game.html")

# ---------- WAIT FOR PLAYER 2 ----------
@app.route("/wait/<game_code>")
def wait(game_code):
    if session.get("player") != "Player 1":
        return redirect(url_for("home"))

    with get_db() as conn:
        ready = conn.execute(
            "SELECT player2_ready FROM games WHERE game_code=?",
            (game_code,)
        ).fetchone()

    if ready and ready[0] == 1:
        return redirect(url_for("secret", game_code=game_code))

    return render_template("wait.html", game_code=game_code)

# ---------- SECRET ----------
@app.route("/secret/<game_code>", methods=["GET", "POST"])
def secret(game_code):
    if session.get("game_code") != game_code:
        return redirect(url_for("home"))

    player = session["player"]

    if request.method == "POST":
        s = request.form["secret"]

        if not valid_number(s):
            return render_template("submit_secret.html", player=player, message="Invalid number")

        with get_db() as conn:
            if player == "Player 1":
                conn.execute("""
                    UPDATE games SET player1_secret=?, player1_ready=1
                    WHERE game_code=?
                """, (s, game_code))
            else:
                conn.execute("""
                    UPDATE games SET player2_secret=?, player2_ready=1
                    WHERE game_code=?
                """, (s, game_code))

            p1, p2 = conn.execute(
                "SELECT player1_ready, player2_ready FROM games WHERE game_code=?",
                (game_code,)
            ).fetchone()

        if p1 and p2:
            return redirect(url_for("game", game_code=game_code))

        return render_template("wait_opponent.html", player=player)

    return render_template("submit_secret.html", player=player)

# ---------- GAME ----------
@app.route("/game/<game_code>", methods=["GET", "POST"])
def game(game_code):
    if session.get("game_code") != game_code:
        return redirect(url_for("home"))

    with get_db() as conn:
        game = conn.execute(
            "SELECT * FROM games WHERE game_code=?", (game_code,)
        ).fetchone()

        history = conn.execute(
            "SELECT player, guess, x, y FROM guesses WHERE game_id=?",
            (game[0],)
        ).fetchall()

    turn_player = "Player 1" if game[6] % 2 == 1 else "Player 2"
    message = ""

    if request.method == "POST":
        if session["player"] != turn_player:
            message = "Not your turn"
        else:
            guess = request.form["guess"]
            if not valid_number(guess):
                message = "Invalid guess"
            else:
                secret = game[2] if turn_player == "Player 1" else game[1]
                x, y = feedback(secret, guess)

                with get_db() as conn:
                    conn.execute("""
                        INSERT INTO guesses (game_id, player, guess, x, y)
                        VALUES (?, ?, ?, ?, ?)
                    """, (game[0], turn_player, guess, x, y))

                    if y == 4:
                        conn.execute(
                            "UPDATE games SET winner=? WHERE game_id=?",
                            (turn_player, game[0])
                        )
                        return render_template(
                            "winner.html",
                            winner=turn_player,
                            secret1=game[1],
                            secret2=game[2]
                        )

                    conn.execute(
                        "UPDATE games SET turn=turn+1 WHERE game_id=?",
                        (game[0],)
                    )

        return redirect(url_for("game", game_code=game_code))

    return render_template(
        "game.html",
        history=history,
        turn_player=turn_player,
        player=session["player"],
        message=message
    )

# ---------- HEALTH ----------
@app.route("/healthz")
def healthz():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True)
