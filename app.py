from flask import Flask, render_template, request, abort, redirect, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import traceback
import os
from dotenv import load_dotenv
import emoji

load_dotenv("keys.env")

app = Flask(__name__)
DB_EXECUTOR = ThreadPoolExecutor(max_workers=1)
VALID_ANALYTICS = ["views", "likes", "exits", "retention_percent"]
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, row):
        self.id = str(row["id"])
        self.username = row["username"]
        self.password_hash = row["password_hash"]


@login_manager.user_loader
def load_user(user_id):
    rows = query_safe("SELECT * FROM users WHERE id = ?", (user_id,))
    if not rows:
        return None
    return User(rows[0])


@app.context_processor
def inject_global_functions():
    def has_liked():
        try:
            return bool(query_safe("SELECT * FROM user_likes WHERE user_id = ? AND song_id = ?", (current_user.get_id(), session.get("id") or -1)))
        except sqlite3.OperationalError:
            abort(500)
    # Return a dictionary exposing the function to Jinja
    return dict(has_liked=has_liked)

def has_emoji(text):
    return bool(emoji.distinct_emoji_list(text))

def sqlite_worker(query: str, values: tuple = tuple()):
    conn = sqlite3.connect('wavevgm.db')
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(query, values)
        conn.commit()
        return_values = cursor.fetchall()
        return return_values
    finally:
        conn.close()


def query_safe(query: str, values: tuple = tuple()):
    future = DB_EXECUTOR.submit(sqlite_worker, query, values)
    return [dict(i) for i in future.result()]


@app.route('/')
def index():
    albums = query_safe("SELECT * FROM albums LIMIT 10")
    return render_template('index.html', albums=albums)

@app.route('/album')
def album_page():
    album_id = request.args.get('id')
    if not album_id:
        abort(400)
    try:
        album_info = query_safe("SELECT * FROM albums WHERE id = ?", (album_id,))[0]
    except IndexError:
        abort(404)
    songs = query_safe("SELECT * FROM songs WHERE album_id = ?", (album_id,))
    return render_template('album.html', album=album_info, songs=songs)

# Author: Gemini (Me for most, Gemini for fts5 search ranking)
@app.route('/search')
def search_page():
    q = request.args.get('q', '').strip()  # Fallback to empty string if missing

    if not q:
        abort(400)

    # Split query strings cleanly by spaces
    words = [w.strip() for w in q.split() if w.strip()]

    if not words:
        # FIXED: Pass empty lists to the template instead of returning raw []
        return render_template('search.html', songs=[], albums=[], q=q)

    # FIXED: Escaped quotes correctly to prevent Python interpretation syntax errors
    safe_words = [f'"{w.replace("\"", "\"\"")}"' for w in words]
    final_query = " OR ".join(safe_words)

    # Executing parallel queries safely across your workspace threads
    songs = query_safe("""
                       SELECT songs.*, game, img_src
                       FROM songs JOIN albums ON songs.album_id = albums.id
                                JOIN songs_fts ON songs.id = songs_fts.rowid
                       WHERE songs_fts.name MATCH ?
                       ORDER BY bm25(songs_fts) ASC;
                       """, (final_query,))

    albums = query_safe("""
                        SELECT albums.*
                        FROM albums
                                 JOIN albums_fts ON albums.id = albums_fts.rowid
                        WHERE albums_fts.name MATCH ?
                        ORDER BY bm25(albums_fts) ASC;
                        """, (final_query,))

    return render_template('search.html', songs=songs, albums=albums, q=q)


@app.route('/api/update-playing-song', methods=["POST"])
def update_playing_song():
    body = request.get_json()
    playing_song = body.get("id")
    session["id"] = playing_song
    return {"Success": True}

@app.route('/api/send-analytics', methods=["POST"])
def update_analytics():
    body = request.get_json()
    analytic_type = body.get("type")
    analytic_id = body.get("id")
    analytic_amount = body.get("amount")
    if not (analytic_type and analytic_amount and analytic_id):
        return {"success": False}, 400
    try:
        if analytic_type == "retention_percent":
            analytic_amount = float(analytic_amount)
        else:
            analytic_amount = int(analytic_amount)
    except ValueError:
        return {"success": False}, 400
    if analytic_type not in VALID_ANALYTICS:
        return {"success": False}, 400
    try:
        if analytic_type == "likes":
            if current_user.is_anonymous:
                return {"success": False}, 401
            user_liked = query_safe("SELECT * FROM user_likes WHERE user_id = ? AND song_id = ?", (current_user.get_id(), analytic_id))
            if user_liked:
                query_safe("UPDATE analytics SET likes = likes - 1 WHERE song_id = ?",(analytic_id,))
                query_safe("DELETE FROM user_likes WHERE user_id = ? AND song_id = ?", (current_user.get_id(), analytic_id))
                return {"success": True}, 200
            elif not user_liked:
                query_safe("UPDATE analytics SET likes = likes + 1 WHERE song_id = ?", (analytic_id,))
                query_safe("INSERT INTO user_likes (user_id, song_id) VALUES (?, ?)", (current_user.get_id(), analytic_id))
                return {"success": True}, 200
            else:
                return {"success": False}, 400
        if analytic_type == "retention_percent":
            if query_safe("SELECT retention_percent FROM analytics WHERE song_id = ?", (analytic_id,))[0]["retention_percent"] == 0:
                query_safe("UPDATE analytics SET retention_percent = ? WHERE song_id = ?", (analytic_amount, analytic_id))
            else:
                query_safe("UPDATE analytics SET retention_percent = (retention_percent + ?) / 2.0 WHERE song_id = ?", (analytic_amount, analytic_id))
        else:
            query_safe(f"UPDATE analytics SET {analytic_type} = {analytic_type} + ? WHERE song_id = ?", (analytic_amount, analytic_id))
    except sqlite3.OperationalError:
        traceback.print_exc()
        return {"success": False}, 500
    return {"success": True}, 200

@app.route("/login", methods=["GET", "POST"])
def login(error = ""):

    if request.method == "POST" and not error:

        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            return login("Missing username or password"), 400

        rows = query_safe("SELECT * FROM users WHERE username = ?", (username,))
        if not rows:
            return login("Invalid credentials"), 401

        user = User(rows[0])

        if not check_password_hash(user.password_hash, password):
            return login("Invalid credentials"), 401

        login_user(user, remember=True)
        return redirect("/", code=303)
    else:
        return render_template("login.html", error=error)


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    if request.method == "POST":
        logout_user()
        return redirect("/", code=303)
    else:
        return render_template("logout.html")

@app.route("/register", methods=["GET", "POST"])
def register(error = ""):
    if request.method == "POST" and not error:
        username = request.form.get("username")
        password = request.form.get("password")
        if not (username and password):
            return register("Missing username or password"), 400
        user_taken = query_safe("SELECT * FROM users WHERE username = ?", (username,))
        if user_taken:
            return register("Username already taken"), 409
        if len(password) < 8:
            return register("Password must contain at least 8 characters"), 400
        if ' ' in password:
            return register("Password cannot contain spaces"), 400
        if not any(char.isdigit() for char in password):
            return register("Password must contain at least one number"), 400
        if not any(char.isalpha() for char in password):
            return register("Password must contain at least one letter"), 400
        if has_emoji(password):
            return register("Password cannot contain emojis"), 400
        password_hash = generate_password_hash(password)
        query_safe("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        rows = query_safe("SELECT * FROM users WHERE username = ?", (username,))
        if not rows:
            return register("An unknown error has occurred. You have not been registered. Please try again."), 500
        user = User(rows[0])
        if not check_password_hash(user.password_hash, password):
            return register("An unknown error has occurred. You have been registered, however, the data seems to be corrupted. Please try logging in from the login screen. If that doesn't work, please create a different account."), 500
        login_user(user, remember=True)
        return redirect("/", code=303)
    else:
        return render_template("./register.html", error=error)
@app.route("/me")
@login_required
def me():
    return {
        "id": current_user.id,
        "username": current_user.username
    }, 200


if __name__ == '__main__':
    app.run()
