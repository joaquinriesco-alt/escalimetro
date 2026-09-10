#!/usr/bin/env python3
"""E26 §11 — servidor mínimo para la Review Console. Sólo biblioteca estándar.

    python3 tools/e26_review_server.py
    → abre http://127.0.0.1:8765/review/

Sirve el repo como archivos estáticos y acepta UN POST: /save, que valida contra
contracts/human_review_v1.schema.json y escribe cada revisión en
cases/<case_id>/reviews/E26/review_<brief>_<alt>.json

Sin login, sin base de datos, sin usuarios. Escucha SÓLO en 127.0.0.1.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "contracts", "human_review_v1.schema.json")
PUERTO = int(os.environ.get("E26_PORT", "8765"))
SEGURO = re.compile(r"^[A-Za-z0-9_.-]+$")


def valida(rev: dict) -> str:
    """Validación contra el contrato. Usa jsonschema si está; si no, comprueba lo esencial a mano."""
    esquema = json.load(open(SCHEMA, encoding="utf-8"))
    try:
        import jsonschema
        jsonschema.validate(rev, esquema)
        return ""
    except ImportError:
        req = esquema.get("required", [])
        falta = [k for k in req if k not in rev]
        if falta:
            return f"faltan campos obligatorios: {falta}"
        props = esquema.get("properties", {})
        for k, v in rev.items():
            if k not in props:
                return f"campo fuera del contrato: {k}"
            enum = props[k].get("enum")
            if enum and v not in enum:
                return f"{k}={v!r} no está en {enum}"
            it = (props[k].get("items") or {}).get("enum")
            if it and isinstance(v, list):
                malo = [x for x in v if x not in it]
                if malo:
                    return f"{k}: valores fuera del contrato {malo}"
        return ""
    except Exception as e:                                   # jsonschema.ValidationError
        return str(e)


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if "POST" in (args[0] if args else ""):
            super().log_message(fmt, *args)

    def do_POST(self):
        if self.path.rstrip("/") != "/save":
            self.send_error(404); return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            lote = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            return self._json(400, {"error": f"JSON inválido: {e}"})
        revs = lote.get("reviews") or []
        if not revs:
            return self._json(400, {"error": "el lote no trae ninguna revisión"})
        escritos = []
        for r in revs:
            err = valida(r)
            if err:
                return self._json(400, {"error": f"{r.get('case_id')}/{r.get('alternative')}: {err}"})
            cid, bid, alt = r.get("case_id", ""), r.get("brief_id", ""), r.get("alternative", "")
            if not all(SEGURO.match(str(x) or "") for x in (cid, bid, alt)):
                return self._json(400, {"error": "identificadores no seguros para nombre de archivo"})
            d = os.path.join(ROOT, "cases", cid, "reviews", "E26")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, f"review_{bid}_{alt}.json")
            json.dump(r, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            escritos.append(os.path.relpath(p, ROOT).replace(os.sep, "/"))
        if lote.get("best_alternative"):
            d = os.path.join(ROOT, "cases", "E26")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, "E26_BEST_ALTERNATIVE.json")
            json.dump({"reviewer": lote.get("reviewer"),
                       "reviewed_at": lote.get("reviewed_at") or
                                      datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "best_alternative": lote["best_alternative"]},
                      open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            escritos.append(os.path.relpath(p, ROOT).replace(os.sep, "/"))
        return self._json(200, {"written": escritos})

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def main():
    idx = os.path.join(ROOT, "review", "review_index.json")
    if not os.path.exists(idx):
        print("falta review/review_index.json — corre primero:\n"
              "  PYTHONPATH=src python3 tools/e26_build_review.py", file=sys.stderr)
        return 1
    srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), H)
    print(f"Review Console en  http://127.0.0.1:{PUERTO}/review/")
    print("Ctrl-C para parar. Las revisiones se guardan en cases/<case>/reviews/E26/.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nlisto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
