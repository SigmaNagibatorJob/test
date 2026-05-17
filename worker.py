import os, json, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), "wave-music-downloads")
PLAYLISTS_FILE = os.path.join(DOWNLOADS_DIR, "playlists.json")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

def load_playlists():
    if os.path.exists(PLAYLISTS_FILE):
        with open(PLAYLISTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_playlists(data):
    with open(PLAYLISTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def run_ytdlp(args):
    result = subprocess.run(["yt-dlp"] + args, capture_output=True, text=True)
    return result.stdout.strip(), result.returncode

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Поиск
        if parsed.path == "/search":
            q = params.get("q", [""])[0]
            if not q:
                return self.send_json({"error": "no query"}, 400)
            out, code = run_ytdlp([f"ytsearch10:{q}", "--dump-json", "--flat-playlist", "--no-warnings", "--quiet"])
            results = []
            for line in out.splitlines():
                try:
                    item = json.loads(line)
                    results.append({
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "artist": item.get("uploader", item.get("channel", "Unknown")),
                        "duration": item.get("duration"),
                        "thumbnail": item.get("thumbnail")
                    })
                except:
                    continue
            return self.send_json(results)

        # Получить URL для стрима
        elif parsed.path == "/audio-url":
            vid = params.get("id", [""])[0]
            if not vid:
                return self.send_json({"error": "no id"}, 400)
            local_path = os.path.join(DOWNLOADS_DIR, f"{vid}.mp3")
            if os.path.exists(local_path):
                return self.send_json({"url": f"file://{local_path}", "local": True})
            out, code = run_ytdlp([
                f"https://www.youtube.com/watch?v={vid}",
                "--get-url", "--format", "bestaudio/best", "--no-warnings", "--quiet"
            ])
            if code != 0 or not out:
                return self.send_json({"error": "failed"}, 500)
            return self.send_json({"url": out.splitlines()[0], "local": False})

        # Скачать трек
        elif parsed.path == "/download":
            vid = params.get("id", [""])[0]
            if not vid:
                return self.send_json({"error": "no id"}, 400)
            local_path = os.path.join(DOWNLOADS_DIR, f"{vid}.mp3")
            if os.path.exists(local_path):
                return self.send_json({"status": "already_downloaded", "path": local_path})
            out, code = run_ytdlp([
                f"https://www.youtube.com/watch?v={vid}",
                "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0",
                "-o", os.path.join(DOWNLOADS_DIR, f"{vid}.%(ext)s"),
                "--no-warnings", "--quiet"
            ])
            if code != 0:
                return self.send_json({"error": "download failed"}, 500)
            return self.send_json({"status": "ok", "path": local_path})

        # Список скачанных
        elif parsed.path == "/downloaded":
            files = []
            if os.path.exists(DOWNLOADS_DIR):
                for f in os.listdir(DOWNLOADS_DIR):
                    if f.endswith(".mp3"):
                        vid = f.replace(".mp3", "")
                        files.append({"id": vid, "path": os.path.join(DOWNLOADS_DIR, f)})
            return self.send_json(files)

        # Получить все плейлисты
        elif parsed.path == "/playlists":
            return self.send_json(load_playlists())

        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = {}
        if length:
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
            except:
                pass
        parsed = urlparse(self.path)

        # Создать плейлист
        if parsed.path == "/playlist/create":
            name = body.get("name", "").strip()
            if not name:
                return self.send_json({"error": "no name"}, 400)
            playlists = load_playlists()
            pid = str(len(playlists) + 1) + "_" + name.replace(" ", "_")
            if pid in playlists:
                return self.send_json({"error": "exists"}, 400)
            playlists[pid] = {"name": name, "tracks": []}
            save_playlists(playlists)
            return self.send_json({"id": pid, "name": name, "tracks": []})

        # Добавить трек в плейлист
        elif parsed.path == "/playlist/add":
            pid = body.get("pid")
            track = body.get("track")
            if not pid or not track:
                return self.send_json({"error": "missing pid or track"}, 400)
            playlists = load_playlists()
            if pid not in playlists:
                return self.send_json({"error": "playlist not found"}, 404)
            # не дублируем
            if not any(t.get("id") == track.get("id") for t in playlists[pid]["tracks"]):
                playlists[pid]["tracks"].append(track)
                save_playlists(playlists)
            return self.send_json({"status": "ok"})

        # Удалить трек из плейлиста
        elif parsed.path == "/playlist/remove-track":
            pid = body.get("pid")
            track_id = body.get("trackId")
            if not pid or not track_id:
                return self.send_json({"error": "missing fields"}, 400)
            playlists = load_playlists()
            if pid not in playlists:
                return self.send_json({"error": "not found"}, 404)
            playlists[pid]["tracks"] = [t for t in playlists[pid]["tracks"] if t.get("id") != track_id]
            save_playlists(playlists)
            return self.send_json({"status": "ok"})

        else:
            self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Удалить плейлист
        if parsed.path == "/playlist":
            pid = params.get("pid", [""])[0]
            if not pid:
                return self.send_json({"error": "no pid"}, 400)
            playlists = load_playlists()
            if pid in playlists:
                del playlists[pid]
                save_playlists(playlists)
            return self.send_json({"status": "ok"})

        else:
            self.send_json({"error": "not found"}, 404)

if __name__ == "__main__":
    port = 8765
    print(f"[wave-worker] запущен на http://127.0.0.1:{port}")
    print(f"[wave-worker] папка загрузок: {DOWNLOADS_DIR}")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
