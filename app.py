from flask import Flask, render_template, request, redirect, url_for, session
import random
import string

app = Flask(__name__)
app.secret_key = "super-secret-key"

games = {}

# ---------------- HELPERS ----------------

def generate_game_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def evaluate_guess(secret, guess):
    correct_position = sum(s == g for s, g in zip(secret, guess))
    correct_digits = sum(min(secret.count(d), guess.count(d)) for d in set(guess))
    return correct_digits, correct_position

# ---------------- ROUTES ----------------

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        session.clear()
        session["player_name"] = request.form["name"]
        return redirect(url_for("index"))
    return render_template("home.html")

@app.route("/index")
def index():
    return render_template("index.html")

@app.route("/create", methods=["POST"])
def create_game():
    game_code = generate_game_code()

    games[game_code] = {
        "players": {
            "P1": {"name": session["player_name"], "secret": None},
            "P2": {"name": None, "secret": None}
        },
        "turn": "P1",
        "guesses": [],
        "status": "waiting",  # waiting → secrets → playing → finished
        "winner": None
    }

    session["game_code"] = game_code
    session["role"] = "P1"

    return redirect(url_for("wait", game_code=game_code))

@app.route("/join", methods=["GET", "POST"])
def join_game():
    if request.method == "POST":
        code = request.form["game_code"].upper()

        if code not in games:
            return render_template("join_game.html", error="Invalid game code")

        game = games[code]
        if game["players"]["P2"]["name"]:
            return render_template("join_game.html", error="Game already full")

        game["players"]["P2"]["name"] = session["player_name"]
        game["status"] = "secrets"

        session["game_code"] = code
        session["role"] = "P2"

        return redirect(url_for("submit_secret", game_code=code))

    return render_template("join_game.html")

@app.route("/wait/<game_code>")
def wait(game_code):
    game = games[game_code]
    if game["status"] == "secrets":
        return redirect(url_for("submit_secret", game_code=game_code))
    return render_template("wait.html", game_code=game_code)

@app.route("/secret/<game_code>", methods=["GET", "POST"])
def submit_secret(game_code):
    game = games[game_code]
    role = session["role"]

    if game["players"][role]["secret"]:
        return redirect(url_for("game", game_code=game_code))

    if request.method == "POST":
        secret = request.form["secret"]
        game["players"][role]["secret"] = secret

        if game["players"]["P1"]["secret"] and game["players"]["P2"]["secret"]:
            game["status"] = "playing"
            return redirect(url_for("game", game_code=game_code))

    return render_template(
        "submit_secret.html",
        player=game["players"][role]["name"]
    )

@app.route("/game/<game_code>", methods=["GET", "POST"])
def game(game_code):
    game = games[game_code]
    role = session["role"]

    if game["status"] == "finished":
        return redirect(url_for("winner", game_code=game_code))

    if request.method == "POST" and game["turn"] == role:
        guess = request.form["guess"]
        opponent = "P2" if role == "P1" else "P1"
        secret = game["players"][opponent]["secret"]

        correct, position = evaluate_guess(secret, guess)

        game["guesses"].append({
            "player": game["players"][role]["name"],
            "guess": guess,
            "correct": correct,
            "position": position
        })

        if position == 4:
            game["status"] = "finished"
            game["winner"] = game["players"][role]["name"]
        else:
            game["turn"] = opponent

    return render_template(
        "game.html",
        game=game,
        role=role,
        player_name=game["players"][role]["name"]
    )

@app.route("/winner/<game_code>")
def winner(game_code):
    game = games[game_code]
    return render_template(
        "winner.html",
        winner=game["winner"],
        secret1=game["players"]["P1"]["secret"],
        secret2=game["players"]["P2"]["secret"]
    )

if __name__ == "__main__":
    app.run(debug=True)
