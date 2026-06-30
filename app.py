import math

from flask import Flask, render_template, request, abort, redirect, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import traceback
import os
from dotenv import load_dotenv
import emoji

# Me
load_dotenv("keys.env")

app = Flask(__name__)
# Gemini
DB_EXECUTOR = ThreadPoolExecutor(max_workers=1)
# Me
VALID_ANALYTICS = ["views", "likes", "exits", "retention_percent"]
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
#ChatGPT
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# Author: ChatGPT
class User(UserMixin):
    def __init__(self, row):
        self.id = str(row["id"])
        self.username = row["username"]
        self.password_hash = row["password_hash"]


# Author: ChatGPT
@login_manager.user_loader
def load_user(user_id):
    rows = query_safe("SELECT * FROM users WHERE id = ?", (user_id,))
    if not rows:
        return None
    return User(rows[0])


# Author: me
@app.context_processor
def inject_global_functions():
    def has_liked():
        try:
            return bool(query_safe("SELECT * FROM user_likes WHERE user_id = ? AND song_id = ?", (current_user.get_id(), session.get("id") or -1)))
        except sqlite3.OperationalError:
            abort(500)
    # Return a dictionary exposing the function to Jinja
    return dict(has_liked=has_liked)

# Author: me
def has_emoji(text):
    return bool(emoji.distinct_emoji_list(text))

# Author: me
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

# Author: me
def query_safe(query: str, values: tuple = tuple()):
    future = DB_EXECUTOR.submit(sqlite_worker, query, values)
    return [dict(i) for i in future.result()]

# Author: me/gemini (gemini for joining dicts for algorithm, me for everything else)
@app.route('/')
def index():
    if current_user.is_authenticated:
        user_global_retention = query_safe("SELECT * FROM user_global_retention WHERE user_id = ?", (current_user.get_id(),))[0]["retention_percent"]
        songs_album = [{"song_id" : i["id"], "album_id" : i["album_id"]} for i in query_safe("SELECT * FROM songs")]
        user_retention_song_ratio = [{"song_id" : i["song_id"], "user_retention_song_ratio" : min(i["retention_percent"] / user_global_retention, 1.5) / 1.5} for i in query_safe("SELECT * FROM user_retention WHERE user_id = ?", (current_user.get_id(),))]
        user_retention_album_ratio = [{"album_id": i["album_id"], "user_retention_album_ratio" : min(i["retention_percent"] / user_global_retention, 1.5) / 1.5} for i in query_safe("SELECT album_id, AVG(retention_percent) as retention_percent FROM user_retention WHERE user_id = ? GROUP BY album_id", (current_user.get_id(),))]
        user_liked_songs = [i["song_id"] for i in query_safe("SELECT song_id FROM user_likes WHERE user_id = ?", (current_user.get_id(),))]
        user_liked = [{"song_id" : i["id"], "liked" : 1 if i["id"] in user_liked_songs else 0} for i in query_safe("SELECT * FROM songs")]
        global_retention_percentage = [{"song_id" : i["song_id"], "global_retention_ratio" : i["retention_percent"]} for i in query_safe("SELECT song_id, retention_percent FROM analytics")]
        max_views = query_safe("SELECT views FROM analytics ORDER BY views DESC LIMIT 1")[0]["views"]
        normalized_views = [{"song_id" : i["song_id"], "views_normalized" : math.log(i["views"] + 1)/math.log(max_views + 1)} for i in query_safe("SELECT song_id, views FROM analytics")]
        # Gemini
        # =====================================================================
        # --- STEP 1: Build Index Maps for O(1) Lookups ---
        # =====================================================================
        # Song-specific lookups (Keyed by song_id)
        song_ratio_map = {i["song_id"]: i["user_retention_song_ratio"] for i in user_retention_song_ratio}
        liked_map = {i["song_id"]: i["liked"] for i in user_liked}
        global_ret_map = {i["song_id"]: i["global_retention_ratio"] for i in global_retention_percentage}
        views_map = {i["song_id"]: i["views_normalized"] for i in normalized_views}

        # Album generic lookup (Keyed by album_id)
        album_ratio_map = {i["album_id"]: i["user_retention_album_ratio"] for i in user_retention_album_ratio}

        # =====================================================================
        # --- STEP 2: Combine Everything Using the Bridge (songs_album) ---
        # =====================================================================
        joined_songs_metrics = []

        for item in songs_album:
            sid = item["song_id"]
            aid = item["album_id"]

            # Using .get() fallback ensures your code won't crash if a song has
            # no analytics records, no likes, or no user retention history yet.
            combined_row = {
                "song_id": sid,
                "album_id": aid,
                "user_retention_song_ratio": song_ratio_map.get(sid, 0.0),
                "user_retention_album_ratio": album_ratio_map.get(aid, 0.0),  # Generic data linked via aid
                "liked": liked_map.get(sid, 0),
                "global_retention_ratio": global_ret_map.get(sid, 0.0),
                "views_normalized": views_map.get(sid, 0.0)
            }

            joined_songs_metrics.append(combined_row)

        # me
        scores = {i["song_id"] : (i["user_retention_song_ratio"] * 0.4) + (i["user_retention_album_ratio"] * 0.25) + (i["liked"] * 0.2) + (i["global_retention_ratio"] * 0.1) + (i["views_normalized"] * 0.05) for i in joined_songs_metrics}
        query_safe("CREATE TEMP TABLE for_you_scores (id INT, score NUMERIC)")
        conn = sqlite3.connect('wavevgm.db', check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("ATTACH DATABASE ':memory:' AS temp_db")
            cursor.execute("CREATE TABLE temp_db.scores (song_id INT, score NUMERIC)")
            cursor.executemany("INSERT INTO temp_db.scores VALUES (?, ?)", scores.items())
            cursor.execute("SELECT songs.*, albums.img_src, albums.game FROM songs JOIN temp_db.scores temp_db ON songs.id = temp_db.song_id JOIN albums ON songs.album_id = albums.id ORDER BY score DESC LIMIT 10")
            for_you = [dict(i) for i in cursor.fetchall()]
            conn.commit()
            cursor.execute("DETACH DATABASE temp_db")
        except sqlite3.OperationalError:
            for_you = query_safe("SELECT songs.*, albums.img_src, albums.game FROM songs JOIN albums ON songs.album_id = albums.id JOIN analytics ON songs.id = analytics.song_id ORDER BY likes DESC LIMIT 10")
        finally:
            conn.close()
    else:
        for_you = query_safe("SELECT songs.*, albums.img_src, albums.game FROM songs JOIN albums ON songs.album_id = albums.id JOIN analytics ON songs.id = analytics.song_id ORDER BY likes DESC LIMIT 10")
    top_10 = query_safe("SELECT name, game, img_src, stream_src, songs.id AS id FROM songs JOIN albums ON songs.album_id = albums.id JOIN analytics ON analytics.song_id = songs.id ORDER BY analytics.views DESC LIMIT 10")
    return render_template('index.html', for_you=for_you, top_10=top_10)

# Author: Me
@app.route('/album')
def album_page():
    album_id = request.args.get('id')
    if not album_id:
        abort(400)
    try:
        album_info = query_safe("SELECT * FROM albums WHERE id = ?", (album_id,))[0]
    except IndexError:
        abort(404)
    songs = query_safe("SELECT songs.*, views FROM songs JOIN analytics ON songs.id = analytics.song_id WHERE album_id = ?", (album_id,))
    return render_template('album.html', album=album_info, songs=songs)

# Author: Gemini and me (Me for most, Gemini for fts5 search ranking)
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


# API stuff

# Author: me
@app.route('/api/get-album-list', methods=["POST"])
def get_album_list():
    body = request.get_json()
    album_name = body.get("name")
    if album_name is None:
        abort(400)
    try:
        album_id = query_safe("SELECT id FROM albums WHERE game = ?", (album_name,))[0]["id"]
        return {"list": query_safe("SELECT stream_src AS stream, img_src AS imgSrc, name AS title, game, songs.id AS songId FROM songs JOIN albums ON songs.album_id = albums.id WHERE album_id = ?", (album_id,))}
    except IndexError or KeyError:
        abort(400)
    except sqlite3.OperationalError:
        abort(500)

# Author: me
@app.route('/api/update-playing-song', methods=["POST"])
def update_playing_song():
    body = request.get_json()
    playing_song = body.get("id")
    session["id"] = playing_song
    return {"Success": True}

# Author: me
@app.route('/api/has-liked', methods=["POST"])
def has_liked():
    body = request.get_json()
    try:
        return {"liked": bool(query_safe("SELECT * FROM user_likes WHERE user_id = ? AND song_id = ?",
                               (current_user.get_id(), body.get("id") or -1)))}
    except sqlite3.OperationalError:
        abort(500)


# Author: me
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
                query_safe("UPDATE user_global_retention SET retention_percent = ? WHERE user_id = ?",(analytic_amount, current_user.get_id()))
            else:
                query_safe("UPDATE analytics SET retention_percent = (retention_percent + ?) / 2.0 WHERE song_id = ?", (analytic_amount, analytic_id))
                query_safe("UPDATE user_global_retention SET retention_percent = (retention_percent + ?) / 2.0 WHERE user_id = ?",(analytic_amount, current_user.get_id()))
            query_safe("INSERT INTO user_retention (user_id, song_id, album_id, retention_percent) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, song_id) DO UPDATE SET retention_percent = ?", (current_user.get_id(), analytic_id, query_safe("SELECT album_id FROM songs WHERE id = ?", (analytic_id,))[0]["album_id"], analytic_amount, analytic_amount))
        else:
            query_safe(f"UPDATE analytics SET {analytic_type} = {analytic_type} + ? WHERE song_id = ?", (analytic_amount, analytic_id))
    except sqlite3.OperationalError:
        traceback.print_exc()
        return {"success": False}, 500
    return {"success": True}, 200

# Author: ChatGPT / me (me for get, gpt for post and login stuff)
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


# Author: ChatGPT (me for get, gpt for post)
@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    if request.method == "POST":
        logout_user()
        return redirect("/", code=303)
    else:
        return render_template("logout.html")

# Author: me
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

# Author: ChatGPT
@app.route("/me")
@login_required
def me():
    return {
        "id": current_user.id,
        "username": current_user.username
    }, 200


if __name__ == '__main__':
    app.run()
