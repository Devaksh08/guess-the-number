from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import random
import string

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "database.db")

# --------------------------
# Initialize database
# --------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_code TEXT UNIQUE,
            player1_joined INTEGER DEFAULT 1,
            player2_joined INTEGER DEFAULT 0,
            player1_secret TEXT,
            player2_secret TEXT,
            player1_ready INTEGER DEFAULT 0,
            player2_ready INTEGER DEFAULT 0,
            turn INTEGER DEFAULT 1,
            winner TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS guesses (
            guess_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            player TEXT NOT NULL,
            guess TEXT NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            FOREIGN KEY(game_id) REFERENCES games(game_id)
        )
    ''')

    conn.commit()
    conn.close()

init_db()

# --------------------------
# Helpers
# --------------------------
def valid_number(num):
    return len(num) == 4 and all(d in "123456789" for d in num) and len(set(num)) == 4

def get_feedback(secret, guess):
    x = sum(d in secret for d in guess)
    y = sum(secret[i] == guess[i] for i in range(4))
    return x, y

def generate_game_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

# --------------------------
# Routes
# --------------------------
@app.route("/")
def home():
    return render_template("home.html")

# --------------------------
# Create Game (Player 1)
# --------------------------
@app.route("/create", methods=["GET", "POST"])
def create_game():
    if request.method == "POST":
        game_code = generate_game_code()

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO games (game_code) VALUES (?)", (game_code,))
        conn.commit()
        conn.close()

        session.clear()
        session["game_code"] = game_code
        session["player"] = "Player 1"

        return redirect(url_for("wait_for_player2", game_code=game_code))

    return render_template("create_game.html")

# --------------------------
# Wait for Player 2
# --------------------------
@app.route("/wait/<game_code>")
def wait_for_player2(game_code):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT player2_joined FROM games WHERE game_code=?", (game_code,))
    row = c.fetchone()
    conn.close()

    if row and row[0] == 1:
        return redirect(url_for("submit_secret", game_code=game_code, player="Player 1"))

    return render_template("wait.html", game_code=game_code)

# --------------------------
# Join Game (Player 2)
# --------------------------
@app.route("/join", methods=["GET", "POST"])
def join_game():
    if request.method == "POST":
        game_code = request.form.get("game_code").upper()

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT player2_joined FROM games WHERE game_code=?", (game_code,))
        row = c.fetchone()

        if not row:
            conn.close()
            return render_template("join_game.html", error="Invalid Game Code")

        if row[0] == 1:
            conn.close()
            return render_template("join_game.html", error="Room already full")

        c.execute("UPDATE games SET player2_joined=1 WHERE game_code=?", (game_code,))
        conn.commit()
        conn.close()

        session.clear()
        session["game_code"] = game_code
        session["player"] = "Player 2"

        return redirect(url_for("submit_secret", game_code=game_code, player="Player 2"))

    return render_template("join_game.html")

# --------------------------
# Submit Secret
# --------------------------
@app.route("/secret/<game_code>/<player>", methods=["GET", "POST"])
def submit_secret(game_code, player):
    if session.get("player") != player:
        return redirect(url_for("home"))

    message = ""

    if request.method == "POST":
        secret = request.form.get("secret")

        if not valid_number(secret):
            message = "Invalid number"
        else:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()

            if player == "Player 1":
                c.execute("UPDATE games SET player1_secret=?, player1_ready=1 WHERE game_code=?",
                          (secret, game_code))
            else:
                c.execute("UPDATE games SET player2_secret=?, player2_ready=1 WHERE game_code=?",
                          (secret, game_code))

            conn.commit()

            c.execute("SELECT player1_ready, player2_ready FROM games WHERE game_code=?", (game_code,))
            r = c.fetchone()
            conn.close()

            if r[0] and r[1]:
                return redirect(url_for("game", game_code=game_code))
            else:
                return redirect(url_for("wait_for_opponent", game_code=game_code, player=player))

    return render_template("submit_secret.html", player=player, message=message)

# --------------------------
# Wait for Opponent Secret
# --------------------------
@app.route("/wait_opponent/<game_code>/<player>")
def wait_for_opponent(game_code, player):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT player1_ready, player2_ready FROM games WHERE game_code=?", (game_code,))
    r = c.fetchone()
    conn.close()

    if (player == "Player 1" and r[1]) or (player == "Player 2" and r[0]):
        return redirect(url_for("game", game_code=game_code))

    return render_template("wait_opponent.html")

# --------------------------
# Gameplay
# --------------------------
@app.route("/game/<game_code>", methods=["GET", "POST"])
def game(game_code):
    if "player" not in session:
        return redirect(url_for("home"))

    player = session["player"]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM games WHERE game_code=?", (game_code,))
    game = c.fetchone()

    game_id = game[0]
    turn_player = "Player 1" if game[8] % 2 == 1 else "Player 2"

    c.execute("SELECT player, guess, x, y FROM guesses WHERE game_id=?", (game_id,))
    history = c.fetchall()

    message = ""

    if request.method == "POST":
        guess = request.form.get("guess")

        if player != turn_player:
            message = "Not your turn"
        elif not valid_number(guess):
            message = "Invalid guess"
        else:
            secret = game[4] if turn_player == "Player 1" else game[3]
            x, y = get_feedback(secret, guess)

            c.execute("INSERT INTO guesses (game_id, player, guess, x, y) VALUES (?, ?, ?, ?, ?)",
                      (game_id, turn_player, guess, x, y))

            if y == 4:
                c.execute("UPDATE games SET winner=? WHERE game_id=?", (turn_player, game_id))
                conn.commit()
                conn.close()
                return render_template("winner.html", winner=turn_player)

            c.execute("UPDATE games SET turn=turn+1 WHERE game_id=?", (game_id,))
            conn.commit()
            return redirect(url_for("game", game_code=game_code))

    conn.close()
    return render_template("game.html", history=history, turn_player=turn_player,
                           player=player, message=message)

# --------------------------
# Health
# --------------------------
@app.route("/healthz")
def healthz():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True)
