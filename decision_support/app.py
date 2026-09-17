"""Interface locale : python -m decision_support.app (depuis la racine)."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

from .engine import DecisionEngine


STATIC = Path(__file__).resolve().parent / "static"


def make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Ne pas journaliser les profils ou les salaires saisis.

        def send_content(self, status, data, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, status, value):
            self.send_content(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                              "application/json; charset=utf-8")

        def local_request(self):
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            return host in allowed and (not origin or origin == f"http://{host}")

        def do_GET(self):
            if not self.local_request():
                return self.send_json(403, {"error": "Accès local uniquement."})
            if self.path == "/api/metadata":
                return self.send_json(200, engine.metadata())
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if self.path not in assets:
                return self.send_json(404, {"error": "Page introuvable."})
            name, mime = assets[self.path]
            self.send_content(200, (STATIC / name).read_bytes(), mime)

        def do_POST(self):
            if not self.local_request():
                return self.send_json(403, {"error": "Accès local uniquement."})
            if self.path != "/api/analyze":
                return self.send_json(404, {"error": "Route inconnue."})
            if self.headers.get_content_type() != "application/json":
                return self.send_json(415, {"error": "Un profil JSON est attendu."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 16_384:
                    return self.send_json(413, {"error": "Taille du profil invalide."})
                payload = json.loads(self.rfile.read(length))
                result = engine.analyze(payload)
                self.send_json(200, result)
            except (ValueError, TypeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception:
                self.send_json(500, {"error": "Le calcul a échoué. Vérifier les fichiers de référence."})

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Aide à la décision salariale — application locale")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 1 et 65535.")
    try:
        engine = DecisionEngine.from_project()
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(engine))
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"Démarrage impossible : {exc}") from exc
    print(f"Ouvrir http://127.0.0.1:{args.port} — Ctrl+C pour arrêter.", flush=True)
    print("Références chargées. Redémarrer après modification des fichiers.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
