from flask import Flask, session, render_template, request, abort, redirect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import traceback
import os
from dotenv import load_dotenv

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
    albums = query_safe("SELECT * FROM albums")
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


@app.route('/search')
def search_page():
    q = request.args.get('q')
    if not q:
        abort(400)
    songs = query_safe("SELECT songs.id AS id, name, game, img_src, stream_src FROM songs JOIN albums ON songs.album_id = albums.id WHERE name LIKE '%' || ? || '%'", (q,))
    albums = query_safe("SELECT * FROM albums WHERE game LIKE '%' || ? || '%'", (q,))
    return render_template('search.html', songs=songs, albums=albums, q=q)

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

        login_user(user)
        return redirect("/"), 200
    else:
        return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return {"success": True}, 200


@app.route("/me")
@login_required
def me():
    return {
        "id": current_user.id,
        "username": current_user.username
    }, 200


if __name__ == '__main__':
    app.run()
