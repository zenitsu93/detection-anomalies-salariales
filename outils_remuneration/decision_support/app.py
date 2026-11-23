"""Interface locale : python -m decision_support.app (depuis la racine)."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import unquote
import webbrowser

from .engine import DecisionEngine


STATIC = Path(__file__).resolve().parent / "static"
ROOT = STATIC.parent.parent

# Les autres pages de l'interface (écran d'accueil, exploration, tableaux de bord), servies par ce
# programme en plus de l'aide à la décision.
# Pourquoi : une page ouverte d'un double-clic (adresse en file:///) n'a pas le droit de demander quoi
# que ce soit à ce programme, le navigateur le refuse. Le bouton « Refaire la détection » du tableau de
# bord ne pourrait donc pas marcher. Ouvertes à l'adresse http://127.0.0.1:8765/..., les pages sont
# « de la même maison » que ce programme, et le bouton marche.
# Les adresses reprennent les chemins des fichiers dans le projet (/accueil.html,
# /output/dashboard/..., /visualisation/...) : les liens entre les pages sont donc les mêmes que
# quand on les ouvre d'un double-clic, ce qui marche toujours.
# Seuls ces types de fichiers sortent : jamais un fichier Excel, donc jamais les données déposées
# dans visualisation/donnees/. Les trois fichiers de input/ ont leur propre adresse (DONNEES, plus bas).
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml"}

# Les fichiers de input/ que la page d'exploration charge toute seule (adresse /api/donnees/<nom>).
DONNEES = ("employes.xlsx", "bands.xlsx", "market.xlsx")

# Une seule détection à la fois : deux clics de suite ne lancent pas deux calculs en même temps.
DETECTION = threading.Lock()


def page_du_projet(adresse):
    """Rend le fichier du projet qui correspond à l'adresse, ou None s'il n'a pas le droit de sortir.
    Exemple : « /output/dashboard/dashboard_anomalies_2026-11-20_11-33-53.html » rend ce fichier ;
    « /input/employes.xlsx » ou « /../autre_dossier/x.html » rendent None."""
    fichier = (ROOT / unquote(adresse.split("?")[0]).lstrip("/")).resolve()
    # Pourquoi regarder le chemin APRÈS resolve() : une adresse avec des « .. » ne peut plus faire
    # semblant d'être dans un dossier permis pour aller lire ailleurs.
    if ROOT not in fichier.parents or fichier.suffix not in TYPES or not fichier.is_file():
        return None
    chemin = fichier.relative_to(ROOT).as_posix()
    permis = (chemin == "accueil.html" or chemin.startswith(("accueil/", "visualisation/"))
              or (chemin.startswith("output/dashboard/") and fichier.suffix == ".html"))
    return fichier if permis else None


def make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Ne pas journaliser les profils ou les salaires saisis.

        def send_content(self, status, data, content_type, strict=True):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            # strict=False pour les autres pages du projet : leur code et leurs styles sont écrits dans
            # la page elle-même (c'est ce qui leur permet de s'ouvrir d'un double-clic), ce que cette
            # règle interdirait.
            if strict:
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
            # Les trois fichiers de input/, pour la page d'exploration : elle les charge toute seule à
            # l'ouverture, au lieu d'attendre qu'on les dépose. Ce sont les mêmes fichiers que ceux de la
            # détection et de l'aide à la décision. Liste fermée : ces trois noms-là, rien d'autre du dossier.
            if self.path.startswith("/api/donnees/"):
                nom = self.path.removeprefix("/api/donnees/")
                fichier = ROOT / "input" / nom
                if nom not in DONNEES or not fichier.is_file():
                    return self.send_json(404, {"error": "Fichier introuvable."})
                return self.send_content(200, fichier.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8"),
                      # Pourquoi : icône de l'onglet et image d'aperçu du lien, servies comme les
                      # autres fichiers (liste fermée, aucun chemin libre lu sur le disque).
                      "/favicon.svg": ("favicon.svg", "image/svg+xml"),
                      "/apercu.png": ("apercu.png", "image/png")}
            if self.path not in assets:
                page = page_du_projet(self.path)
                if page is None:
                    return self.send_json(404, {"error": "Page introuvable."})
                return self.send_content(200, page.read_bytes(), TYPES[page.suffix], strict=False)
            name, mime = assets[self.path]
            self.send_content(200, (STATIC / name).read_bytes(), mime)

        def do_POST(self):
            if not self.local_request():
                return self.send_json(403, {"error": "Accès local uniquement."})
            if self.path == "/api/detection":
                return self.refaire_detection()
            # Les deux questions de la page : le salaire prédit pour un profil (/api/analyze), et le profil
            # d'un salarié retrouvé par son matricule (/api/salarie), pour la vue par salarié.
            if self.path not in ("/api/analyze", "/api/salarie", "/api/matricules"):
                return self.send_json(404, {"error": "Route inconnue."})
            if self.headers.get_content_type() != "application/json":
                return self.send_json(415, {"error": "Un profil JSON est attendu."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 16_384:
                    return self.send_json(413, {"error": "Taille du profil invalide."})
                payload = json.loads(self.rfile.read(length))
                # Les matricules à proposer pendant qu'on tape dans la case « Matricule ».
                if self.path == "/api/matricules":
                    result = engine.matricules(payload.get("texte") if isinstance(payload, dict) else None)
                elif self.path == "/api/salarie":
                    result = engine.salarie(payload.get("matricule") if isinstance(payload, dict) else None)
                else:
                    result = engine.analyze(payload)
                self.send_json(200, result)
            except (ValueError, TypeError) as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception:
                self.send_json(500, {"error": "Le calcul a échoué. Vérifier les fichiers de référence."})

        def refaire_detection(self):
            """Le bouton « Refaire la détection » du tableau de bord : relance la détection sur les
            fichiers de input/, puis rend l'adresse du nouveau tableau de bord."""
            # nonlocal : on remplace le moteur de l'aide à la décision gardé par make_handler.
            nonlocal engine
            if not DETECTION.acquire(blocking=False):
                return self.send_json(409, {"error": "Une détection est déjà en cours."})
            try:
                # Même commande que dans le terminal, avec le même Python que ce programme.
                # PYTHONIOENCODING : pour relire les accents des messages de la détection.
                fait = subprocess.run([sys.executable, str(ROOT / "detection" / "detect_salary_anomalies.py")], cwd=ROOT,
                                      capture_output=True, encoding="utf-8", errors="replace",
                                      env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                if fait.returncode != 0:
                    # La dernière ligne du message d'erreur est celle qui dit ce qui ne va pas.
                    lignes = (fait.stderr or fait.stdout).strip().splitlines()
                    raison = lignes[-1] if lignes else "raison inconnue"
                    return self.send_json(500, {"error": f"La détection s'est arrêtée : {raison}"})
                # Pourquoi recharger aussi l'aide à la décision : elle garde en mémoire les fichiers de
                # input/ lus au démarrage. Si on vient de les remplacer, elle répondrait encore avec les
                # anciens, alors que le tableau de bord montrerait les nouveaux.
                engine = DecisionEngine.from_project()
                # Les noms portent la date et l'heure : le dernier de la liste est le plus récent.
                tableaux = sorted((ROOT / "output" / "dashboard").glob("dashboard_anomalies_*.html"))
                self.send_json(200, {"tableau_de_bord": f"/output/dashboard/{tableaux[-1].name}"})
            except (OSError, ValueError, KeyError, IndexError) as exc:
                self.send_json(500, {"error": f"La détection n'a pas pu être refaite : {exc}"})
            finally:
                DETECTION.release()

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Aide à la décision salariale — application locale")
    parser.add_argument("--port", type=int, default=8765)
    # Pourquoi --ouvrir : lancer_interface.bat veut ouvrir l'écran d'accueil (accueil.html) tout seul.
    # Si le .bat l'ouvrait lui-même avant de lancer ce programme, la carte « Décider d'un salaire »
    # donnerait une erreur pendant les quelques secondes où les références se chargent. Ici, la page
    # ne s'ouvre qu'une fois le programme prêt à répondre, et à son adresse http://127.0.0.1:... (voir
    # TYPES, en haut), pas comme un fichier.
    parser.add_argument("--ouvrir", metavar="PAGE",
                        help="page du projet à ouvrir dans le navigateur une fois le programme prêt (exemple : accueil.html)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 1 et 65535.")
    if args.ouvrir and page_du_projet(args.ouvrir) is None:
        parser.error(f"Page introuvable : {args.ouvrir}")
    try:
        engine = DecisionEngine.from_project()
        # Pourquoi allow_reuse_address = False : sous Windows, sans ça, un deuxième lancement démarre sans
        # erreur sur le même port que le premier, et le navigateur continue de parler au premier, donc à
        # l'ancienne version. Avec ça, le deuxième lancement s'arrête en disant que le port est déjà pris.
        ThreadingHTTPServer.allow_reuse_address = False
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(engine))
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"Démarrage impossible : {exc}") from exc
    print(f"Ouvrir http://127.0.0.1:{args.port} — Ctrl+C pour arrêter.", flush=True)
    print("Références chargées. Après modification des fichiers : redémarrer, ou cliquer sur", flush=True)
    print("« Refaire la détection » dans le tableau de bord.", flush=True)
    if args.ouvrir:
        webbrowser.open(f"http://127.0.0.1:{args.port}/{page_du_projet(args.ouvrir).relative_to(ROOT).as_posix()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
