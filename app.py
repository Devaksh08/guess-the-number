from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os

# --------------------------
# App setup
# --------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "database.db")

# --------------------------
# Database initialization
# --------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1_name TEXT,
            player2_name TEXT,
            player1_secret TEXT,
            player2_secret TEXT,
            turn INTEGER DEFAULT 1,
            winner TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS guesses (
            guess_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            player TEXT NOT NULL,
            guess TEXT NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

# ✅ REQUIRED FOR FLASK 3 / RENDER
init_db()

# --------------------------
# Helpers
# --------------------------
def valid_number(num):
    return (
        len(num) == 4 and
        num.isdigit() and
        all(d in "123456789" for d in num) and
        len(set(num)) == 4
    )

def get_feedback(secret, guess):
    x = sum(d in secret for d in guess)
    y = sum(secret[i] == guess[i] for i in range(4))
    return x, y

# --------------------------
# Routes
# --------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form.get("name")

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute(
            "INSERT INTO games (player1_name) VALUES (?)",
            (name,)
        )
        game_id = c.lastrowid
        conn.commit()
        conn.close()

        session["game_id"] = game_id
        session["player"] = "Player 1"

        return redirect(url_for("secret"))

    return render_template("index.html")


@app.route("/join/<int:game_id>", methods=["GET", "POST"])
def join(game_id):
    if request.method == "POST":
        name = request.form.get("name")

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute(
            "UPDATE games SET player2_name=? WHERE game_id=?",
            (name, game_id)
        )
        conn.commit()
        conn.close()

        session["game_id"] = game_id
        session["player"] = "Player 2"

        return redirect(url_for("secret"))

    return render_template("join.html", game_id=game_id)


@app.route("/secret", methods=["GET", "POST"])
def secret():
    game_id = session.get("game_id")
    player = session.get("player")

    if not game_id or not player:
        return redirect(url_for("index"))

    if request.method == "POST":
        secret = request.form.get("secret")

        if not valid_number(secret):
            return render_template("secret.html", error="Invalid number!")

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        if player == "Player 1":
            c.execute(
                "UPDATE games SET player1_secret=? WHERE game_id=?",
                (secret, game_id)
            )
        else:
            c.execute(
                "UPDATE games SET player2_secret=? WHERE game_id=?",
                (secret, game_id)
            )

        conn.commit()
        conn.close()

        return redirect(url_for("game"))

    return render_template("secret.html")


@app.route("/game", methods=["GET", "POST"])
def game():
    game_id = session.get("game_id")
    player = session.get("player")

    if not game_id or not player:
        return redirect(url_for("index"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT * FROM games WHERE game_id=?", (game_id,))
    game = c.fetchone()

    turn_player = "Player 1" if game[5] % 2 == 1 else "Player 2"

    c.execute(
        "SELECT player, guess, x, y FROM guesses WHERE game_id=? ORDER BY guess_id",
        (game_id,)
    )
    history = c.fetchall()

    message = ""

    if request.method == "POST":
        if player != turn_player:
            message = "Not your turn!"
        else:
            guess = request.form.get("guess")

            if not valid_number(guess):
                message = "Invalid guess!"
            else:
                secret = game[4] if player == "Player 1" else game[3]
                x, y = get_feedback(secret, guess)

                c.execute(
                    "INSERT INTO guesses (game_id, player, guess, x, y) VALUES (?, ?, ?, ?, ?)",
                    (game_id, player, guess, x, y)
                )

                if y == 4:
                    c.execute(
                        "UPDATE games SET winner=? WHERE game_id=?",
                        (player, game_id)
                    )
                else:
                    c.execute(
                        "UPDATE games SET turn=turn+1 WHERE game_id=?",
                        (game_id,)
                    )

                conn.commit()
                conn.close()
                return redirect(url_for("game"))

    conn.close()

    if game[6]:
        return render_template(
            "winner.html",
            winner=game[6],
            secret1=game[3],
            secret2=game[4]
        )

    return render_template(
        "game.html",
        game=game,
        history=history,
        turn_player=turn_player,
        message=message
    )


@app.route("/healthz")
def healthz():
    return "OK", 200


if __name__ == "__main__":
    app.run(debug=True)
