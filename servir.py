"""Servidor local para testar o site. Nao precisa instalar nada.

    python servir.py            -> http://localhost:8000
    python servir.py 8080       -> outra porta
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import webbrowser
from functools import partial
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serve web/ na raiz e expoe dados/ em /dados."""

    def translate_path(self, path):
        limpo = path.split("?", 1)[0].split("#", 1)[0]
        if limpo.startswith("/dados"):
            return str(RAIZ / limpo.lstrip("/"))
        return str(RAIZ / "web" / limpo.lstrip("/") or "index.html")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "404" in (fmt % args):
            super().log_message(fmt, *args)


def main():
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    if not (RAIZ / "dados" / "ranking.json").exists():
        print("Aviso: dados/ranking.json nao existe. Rode antes:  python -m etl.build")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", porta), partial(Handler)) as srv:
        url = f"http://localhost:{porta}"
        print(f"Dignos rodando em {url}  (Ctrl+C para parar)")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        srv.serve_forever()


if __name__ == "__main__":
    main()
