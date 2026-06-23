from flask import Flask, render_template, request, abort
import sqlite3
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
DB_EXECUTOR = ThreadPoolExecutor(max_workers=1)



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


if __name__ == '__main__':
    app.run()
