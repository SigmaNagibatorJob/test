import os
import json
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), "wave-music-downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

def run_ytdlp(args):
    result = subprocess.run(
        ["yt-dlp"] + args,
        capture_output=True, text=True
    )
    return result.stdout.strip(), result.returncode

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # тихий режим

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # GET /search?q=текст
        if parsed.path == "/search":
            q = params.get("q", [""])[0]
            if not q:
                return self.send_json({"error": "no query"}, 400)

            out, code = run_ytdlp([
                f"ytsearch10:{q}",
                "--dump-json", "--flat-playlist",
                "--no-warnings", "--quiet"
            ])
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

        # GET /audio-url?id=VIDEO_ID
        elif parsed.path == "/audio-url":
            vid = params.get("id", [""])[0]
            if not vid:
                return self.send_json({"error": "no id"}, 400)

            # проверяем скачан ли уже
            local_path = os.path.join(DOWNLOADS_DIR, f"{vid}.mp3")
            if os.path.exists(local_path):
                return self.send_json({"url": f"file://{local_path}", "local": True})

            # иначе получаем прямой стрим URL
            out, code = run_ytdlp([
                f"https://www.youtube.com/watch?v={vid}",
                "--get-url", "--format", "bestaudio/best",
                "--no-warnings", "--quiet"
            ])
            if code != 0 or not out:
                return self.send_json({"error": "failed to get url"}, 500)

            url = out.splitlines()[0]
            return self.send_json({"url": url, "local": False})

        # GET /download?id=VIDEO_ID&title=Название
        elif parsed.path == "/download":
            vid = params.get("id", [""])[0]
            title = params.get("title", [vid])[0]
            if not vid:
                return self.send_json({"error": "no id"}, 400)

            local_path = os.path.join(DOWNLOADS_DIR, f"{vid}.mp3")
            if os.path.exists(local_path):
                return self.send_json({"status": "already_downloaded", "path": local_path})

            out, code = run_ytdlp([
                f"https://www.youtube.com/watch?v={vid}",
                "--extract-audio", "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", os.path.join(DOWNLOADS_DIR, f"{vid}.%(ext)s"),
                "--no-warnings", "--quiet"
            ])
            if code != 0:
                return self.send_json({"error": "download failed"}, 500)
            return self.send_json({"status": "ok", "path": local_path})

        # GET /downloaded — список скачанных
        elif parsed.path == "/downloaded":
            files = []
            for f in os.listdir(DOWNLOADS_DIR):
                if f.endswith(".mp3"):
                    vid = f.replace(".mp3", "")
                    files.append({"id": vid, "path": os.path.join(DOWNLOADS_DIR, f)})
            return self.send_json(files)

        else:
            self.send_json({"error": "not found"}, 404)

if __name__ == "__main__":
    port = 8765
    print(f"[wave-worker] запущен на порту {port}")
    print(f"[wave-worker] папка загрузок: {DOWNLOADS_DIR}")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
