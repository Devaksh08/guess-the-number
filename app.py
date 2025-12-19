from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import random
import string

app = Flask(__name__)
app.secret_key = "supersecretkey"

DB_NAME = os.path.join(os.path.dirname(__file__), "database.db")

# --------------------------
# Initialize database
# --------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Create games table
    c.execute('''
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_code TEXT UNIQUE,
            player1_secret TEXT,
            player2_secret TEXT,
            player1_ready INTEGER DEFAULT 0,
            player2_ready INTEGER DEFAULT 0,
            turn INTEGER DEFAULT 1,
            winner TEXT
        )
    ''')

    # Create guesses table
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

# --------------------------
# Helper functions
# --------------------------
def valid_number(num):
    """Check if 4-digit number with digits 1-9 and no repeats"""
    return len(num) == 4 and all(d in "123456789" for d in num) and len(set(num)) == 4

def get_feedback(secret, guess):
    """Return x = correct digits, y = correct position digits"""
    x = sum([1 for d in guess if d in secret])
    y = sum([1 for i in range(4) if guess[i] == secret[i]])
    return x, y

def generate_game_code(length=4):
    """Generate unique game code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# --------------------------
# Routes
# --------------------------

# Home page redirects to create/join options
@app.route("/")
def home():
    return redirect(url_for("create_game"))

# --------------------------
# Create Game - Player 1
# --------------------------
@app.route("/create", methods=["GET", "POST"])
def create_game():
    if request.method == "POST":
        player1_name = request.form.get("player1_name") or "Player 1"
        game_code = generate_game_code()
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO games (game_code) VALUES (?)", (game_code,))
        game_id = c.lastrowid
        conn.commit()
        conn.close()

        session["game_code"] = game_code
        session["player"] = "Player 1"
        session["player_name"] = player1_name
        return redirect(url_for("wait_for_player2", game_code=game_code))

    return render_template("create_game.html")

# --------------------------
# Wait for Player 2 to join
# --------------------------
@app.route("/wait/<game_code>")
def wait_for_player2(game_code):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT player2_secret FROM games WHERE game_code=?", (game_code,))
    row = c.fetchone()
    conn.close()

    player2_secret = row[0] if row else None

    if player2_secret:
        # Player 2 has already submitted secret
        return redirect(url_for("submit_secret", game_code=game_code, player="Player 1"))
    
    return render_template("wait.html", game_code=game_code)

# --------------------------
# Join Game - Player 2
# --------------------------
@app.route("/join", methods=["GET", "POST"])
def join_game():
    if request.method == "POST":
        game_code = request.form.get("game_code").upper()
        player2_name = request.form.get("player2_name") or "Player 2"

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT * FROM games WHERE game_code=?", (game_code,))
        game = c.fetchone()
        conn.close()

        if not game:
            return render_template("join_game.html", error="Invalid Game Code!")
        
        session["game_code"] = game_code
        session["player"] = "Player 2"
        session["player_name"] = player2_name
        return redirect(url_for("submit_secret", game_code=game_code, player="Player 2"))

    return render_template("join_game.html")

# --------------------------
# Submit Secret - Both Players
# --------------------------
@app.route("/secret/<game_code>/<player>", methods=["GET", "POST"])
def submit_secret(game_code, player):
    if "player" not in session or session["player"] != player:
        return redirect(url_for("home"))

    message = ""
    if request.method == "POST":
        secret = request.form.get("secret")
        if not valid_number(secret):
            message = "Invalid number! Must be 4 digits 1-9 with no repeats."
        else:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            if player == "Player 1":
                c.execute("UPDATE games SET player1_secret=?, player1_ready=1 WHERE game_code=?", (secret, game_code))
            else:
                c.execute("UPDATE games SET player2_secret=?, player2_ready=1 WHERE game_code=?", (secret, game_code))
            conn.commit()

            # Check if both players are ready
            c.execute("SELECT player1_ready, player2_ready FROM games WHERE game_code=?", (game_code,))
            row = c.fetchone()
            conn.close()

            if row[0] == 1 and row[1] == 1:
                return redirect(url_for("game", game_code=game_code))
            else:
                return redirect(url_for("wait_for_opponent", game_code=game_code, player=player))

    return render_template("submit_secret.html", player=player, message=message)

# --------------------------
# Wait for Opponent to submit secret
# --------------------------
@app.route("/wait_opponent/<game_code>/<player>")
def wait_for_opponent(game_code, player):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT player1_ready, player2_ready FROM games WHERE game_code=?", (game_code,))
    row = c.fetchone()
    conn.close()

    if (player == "Player 1" and row[1] == 1) or (player == "Player 2" and row[0] == 1):
        return redirect(url_for("game", game_code=game_code))

    return render_template("wait_opponent.html", player=player)

# --------------------------
# Main Gameplay
# --------------------------
@app.route("/game/<game_code>", methods=["GET", "POST"])
def game(game_code):
    if "player" not in session:
        return redirect(url_for("home"))

    player = session["player"]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM games WHERE game_code=?", (game_code,))
    game_data = c.fetchone()

    if not game_data:
        conn.close()
        return redirect(url_for("home"))

    game_id = game_data[0]
    turn_player = "Player 1" if game_data[6] % 2 == 1 else "Player 2"

    # Fetch guess history
    c.execute("SELECT player, guess, x, y FROM guesses WHERE game_id=? ORDER BY guess_id ASC", (game_id,))
    history = c.fetchall()

    message = ""
    if request.method == "POST":
        guess = request.form.get("guess")
        if player != turn_player:
            message = "It's not your turn!"
        elif not valid_number(guess):
            message = "Invalid guess! Must be 4 digits 1-9, no repeats."
        else:
            # Use opponent's secret for feedback
            secret = game_data[2] if turn_player == "Player 1" else game_data[1]

            x, y = get_feedback(secret, guess)

            # Save guess
            c.execute("INSERT INTO guesses (game_id, player, guess, x, y) VALUES (?, ?, ?, ?, ?)",
                      (game_id, turn_player, guess, x, y))

            # Check winner
            if y == 4:
                c.execute("UPDATE games SET winner=? WHERE game_id=?", (turn_player, game_id))
                conn.commit()
                conn.close()
                return render_template("winner.html", winner=turn_player,
                                       secret1=game_data[1], secret2=game_data[2])

            # Increment turn
            c.execute("UPDATE games SET turn=turn+1 WHERE game_id=?", (game_id,))
            conn.commit()
            return redirect(url_for("game", game_code=game_code))

    conn.close()
    return render_template("game.html", game=game_data, history=history, turn_player=turn_player,
                           player=player, message=message)

# --------------------------
# Run app
# --------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
