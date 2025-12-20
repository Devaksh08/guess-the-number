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
def create_game():
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
def join_game():
    if request.method == "POST":
        game_code = request.form.get("game_code", "").upper()
        player_name = request.form.get("player_name", "Player 2")

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT game_id FROM games WHERE game_code=?", (game_code,))
        game = c.fetchone()
        conn.close()

        if not game:
            return render_template("join_game.html", error="Invalid game code!")

        session.clear()
        session["player"] = "Player 2"
        session["player_name"] = player_name
        session["game_code"] = game_code

        return redirect(url_for("submit_secret", game_code=game_code))

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
        return redirect(url_for("submit_secret", game_code=game_code))

    return render_template("wait.html", game_code=game_code)

# ---------- SECRET ----------
@app.route("/secret/<game_code>", methods=["GET", "POST"])
def submit_secret(game_code):
    game = games.get(game_code)

    if not game:
        return "Invalid game code", 404

    # Who is this user?
    player = session.get("player")

    if player not in ["player1", "player2"]:
        return "Player not recognized", 403

    # 🔒 If this player already submitted → wait
    if player == "player1" and game["secret1"]:
        return redirect(url_for("wait_opponent", game_code=game_code))

    if player == "player2" and game["secret2"]:
        return redirect(url_for("wait_opponent", game_code=game_code))

    if request.method == "POST":
        secret = request.form.get("secret")

        # Basic validation
        if (
            not secret.isdigit()
            or len(secret) != 4
            or "0" in secret
            or len(set(secret)) != 4
        ):
            return render_template(
                "submit_secret.html",
                player=player,
                message="Invalid number. Use 4 unique digits from 1-9."
            )

        # ✅ SAVE SECRET CORRECTLY
        if player == "player1":
            game["secret1"] = secret
        else:
            game["secret2"] = secret

        # ✅ If both secrets exist → start game
        if game["secret1"] and game["secret2"]:
            return redirect(url_for("game", game_code=game_code))

        # Otherwise wait
        return redirect(url_for("wait_opponent", game_code=game_code))

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
        game_code=game_code,
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
