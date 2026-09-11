"""E27 — ESCALÍMETRO herramienta interna. Un solo servicio web sobre el motor existente.

Flujo del §3, entero desde Chrome:
    BIBLIOTECA → SUBIR → PREPARAR SHELL → PROGRAMA → GENERAR → VER A/B/C → EVALUAR → GUARDAR

Regla que atraviesa toda la UI: los estados del motor se muestran con su nombre real.
SEARCH_EXHAUSTED significa "no lo encontramos con esta búsqueda", jamás "no cabe" (§9).
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Dict, List

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, url_for)

from . import auth, briefs as briefmod, engine, intake, store

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEWER = os.environ.get("ESCALIMETRO_REVIEWER", "Joaquín Riesco")
MODULES_PATH = os.path.join(REPO_ROOT, "program_templates", "modules_office.json")
#: Etiqueta de la versión de la app que sirve `/healthz`. Es un rótulo nuestro, NO el commit: saber
#: qué build está viva no debería exigir credenciales, y filtrar un SHA de git sí sería de más.
APP_VERSION = "e27.2"
GRADES = [("A_GOOD", "A — LA MANDARÍA"), ("B_CORRECTABLE", "B — CORREGIBLE"),
          ("C_BAD", "C — NO SIRVE")]
#: §12 — las etiquetas son las del contrato, leídas del contrato. No se redefinen aquí.
CONTRACT = os.path.join(REPO_ROOT, "contracts", "human_review_v1.schema.json")


def reason_tags() -> List[str]:
    with open(CONTRACT, encoding="utf-8") as fh:
        return json.load(fh)["properties"]["reason_tags"]["items"]["enum"]


def create_app() -> Flask:
    auth.check_config()
    store.init()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = intake.MAX_UPLOAD_MB * 1024 * 1024 * 4
    engine.start_worker()
    if os.environ.get("ESCALIMETRO_MIGRATE", "1") == "1":
        from . import migrate                                 # noqa: PLC0415
        migrate.run()

    # ---------- helpers -----------------------------------------------------------------------
    def case_or_404(case_id: str):
        row = store.q1("SELECT * FROM cases WHERE case_id=?", (case_id,))
        if row is None:
            abort(404)
        return row

    def alt_or_404(alt: str) -> str:
        if alt not in engine.ALTS:
            abort(404)
        return alt

    @app.context_processor
    def _ctx():
        return {"pending_jobs": engine.pending()}

    # ---------- biblioteca --------------------------------------------------------------------
    @app.get("/")
    @auth.require
    def library():
        rows = store.q("SELECT * FROM cases ORDER BY uploaded_at DESC")
        cases = []
        for r in rows:
            d = dict(r)
            d["runs"] = store.q1("SELECT COUNT(*) n FROM runs WHERE case_id=?", (r["case_id"],))["n"]
            d["reviews"] = store.q1("SELECT COUNT(*) n FROM reviews WHERE case_id=?",
                                    (r["case_id"],))["n"]
            cases.append(d)
        return render_template("library.html", cases=cases, tracks=store.TRACKS)

    @app.post("/upload")
    @auth.require
    def upload():
        files = request.files.getlist("plantas")
        ok, errs = [], []
        for f in files:
            if not f or not f.filename:
                continue
            try:
                ok.append(intake.save_upload(f))
            except intake.IntakeError as e:
                errs.append(f"{f.filename}: {e}")
            except Exception as e:                            # noqa: BLE001
                errs.append(f"{f.filename}: no se pudo guardar ({e!r})")
        if len(ok) == 1 and not errs:
            return redirect(url_for("case_view", case_id=ok[0]))
        return render_template("uploaded.html", ok=ok, errs=errs)

    @app.post("/case/<case_id>/track")
    @auth.require
    def set_track(case_id):
        case_or_404(case_id)
        t = request.form.get("track", "DEVELOPMENT")
        if t not in store.TRACKS:
            abort(400)
        store.ex("UPDATE cases SET track=? WHERE case_id=?", (t, case_id))
        return redirect(request.form.get("next") or url_for("library"))

    # ---------- caso --------------------------------------------------------------------------
    def _render_case(case_id, errors=None, form=None, brief_errors=None, code=200):
        """Una sola función pinta el caso, con o sin errores. Así un POST rechazado vuelve a la
        MISMA pantalla con los campos marcados y lo que el usuario ya había escrito (§2)."""
        c = case_or_404(case_id)
        it = store.q1("SELECT * FROM intake WHERE case_id=?", (case_id,))
        bs = store.q("SELECT * FROM briefs WHERE case_id=? ORDER BY created_at DESC", (case_id,))
        rs = store.q("SELECT * FROM runs WHERE case_id=? ORDER BY created_at DESC", (case_id,))
        runs = []
        for r in rs:
            d = dict(r)
            d["alts"] = [dict(a) for a in store.q(
                "SELECT alt, status FROM alternatives WHERE run_id=? ORDER BY alt", (r["run_id"],))]
            runs.append(d)
        w, h = intake.preview_size(case_id)
        codes = store.js(it["missing"] if it else None, []) or []
        html = render_template(
            "case.html", c=c, it=it, briefs=[dict(b) for b in bs], runs=runs,
            modules=briefmod.MODULE_LABELS, defaults=briefmod.DEFAULT_ROOMS,
            preview_w=w, preview_h=h, missing=intake.humanize_missing(codes),
            existing_scale=intake.existing_scale(case_id),
            has_shell=os.path.exists(os.path.join(store.case_dir(case_id), "outputs",
                                                  "floorplate.json")),
            tracks=store.TRACKS, errors=errors or {}, brief_errors=brief_errors or {},
            confirmed=store.js(it["confirmed"] if it else None, []) or [],
            form=form, required_confirms=intake.REQUIRED_CONFIRMS,
            blockers=intake.blockers_for_generate(case_id))
        return (html, code) if code != 200 else html

    @app.get("/case/<case_id>")
    @auth.require
    def case_view(case_id):
        return _render_case(case_id)

    @app.get("/case/<case_id>/preview.png")
    @auth.require
    def preview(case_id):
        case_or_404(case_id)
        p = os.path.join(store.case_dir(case_id), "preview.png")
        if not os.path.exists(p):
            abort(404)
        return send_file(p, mimetype="image/png")

    @app.get("/case/<case_id>/original")
    @auth.require
    def original(case_id):
        c = case_or_404(case_id)
        d = store.case_dir(case_id)
        if not c["source_file"] or not os.path.exists(os.path.join(d, c["source_file"])):
            abort(404)
        # send_from_directory ancla el directorio: un nombre con ../ no escapa (§17)
        return send_from_directory(d, c["source_file"])

    @app.get("/case/<case_id>/shell.svg")
    @auth.require
    def shell_svg(case_id):
        """§20 — el shell se dibuja desde floorplate.json en cada request. Nunca 404 por un PNG
        que el .gitignore dejó fuera del deploy."""
        case_or_404(case_id)
        svg = intake.shell_svg_for(case_id)
        if svg is None:
            abort(404)
        return app.response_class(svg, mimetype="image/svg+xml")

    @app.post("/case/<case_id>/intake")
    @auth.require
    def save_intake(case_id):
        case_or_404(case_id)
        f = request.form
        # §4 — el servidor decide, no el navegador. Un POST con campos faltantes vuelve a la misma
        # pantalla con los errores marcados y NO llega al pipeline: por eso ya no puede haber un
        # FAILED causado por un input omitido.
        errs = intake.validate_intake_form(f)
        if errs:
            return _render_case(case_id, errors=errs, form=f, code=400)
        seed = _pair(f.get("seed_x"), f.get("seed_y"))
        ent = _pair(f.get("entrance_x"), f.get("entrance_y"))
        px_per_m, method, note = None, None, ""
        p1 = _pair(f.get("scale_x1"), f.get("scale_y1"))
        p2 = _pair(f.get("scale_x2"), f.get("scale_y2"))
        if p1 and p2 and f.get("scale_m"):
            px_per_m = intake.px_per_m_from_two_points(p1, p2, float(f["scale_m"]))
            method, note = "two_points", f'dos puntos + {f["scale_m"]} m declarados'
        area = f.get("published_area_m2") or None
        store.ex("UPDATE cases SET published_area_m2=?, source_name=?, title=? WHERE case_id=?",
                 (float(area) if area else None, f.get("source_name") or None,
                  (f.get("title") or "").strip()[:120] or "Planta", case_id))
        store.ex("UPDATE intake SET declared_clean=?, scale_px_per_m=?, scale_method=?, "
                 "scale_note=?, seed_point=?, entrance_point=?, confirmed=?, updated_at=? "
                 "WHERE case_id=?",
                 (f.get("declared_clean") or None, px_per_m, method, note,
                  json.dumps(seed) if seed else None, json.dumps(ent) if ent else None,
                  json.dumps(f.getlist("confirm")), store.now(), case_id))
        res = intake.normalize(case_id)
        return render_template("intake_result.html", case_id=case_id, res=res,
                               missing=intake.humanize_missing(res["missing"]))

    # ---------- brief y generación ------------------------------------------------------------
    @app.post("/case/<case_id>/brief")
    @auth.require
    def create_brief(case_id):
        case_or_404(case_id)
        f = request.form
        rooms = {m: f.get(f"room_{m}") or 0 for m, _ in briefmod.MODULE_LABELS}
        errs = briefmod.field_errors(f.get("brief_name"), f.get("headcount"),
                                     f.get("workstations"), rooms, MODULES_PATH)
        # §3 — generar exige shell READY. Se comprueba ANTES de escribir nada: si el usuario pidió
        # "guardar y generar" sobre un shell sin preparar, no se crea ni el brief a medias.
        quiere_generar = bool(f.get("generate"))
        bloqueos = intake.blockers_for_generate(case_id) if quiere_generar else []
        if errs or bloqueos:
            if bloqueos:
                errs = dict(errs); errs["generate"] = " ".join(bloqueos)
            return _render_case(case_id, brief_errors=errs, form=f, code=400)
        b = briefmod.build(f.get("brief_name"), f.get("headcount"), f.get("workstations"), rooms)
        bid = f'{b["brief_id"]}_{uuid.uuid4().hex[:4].upper()}'
        b["brief_id"] = bid
        sha = briefmod.write(b, os.path.join(store.case_dir(case_id), "briefs", f"{bid}.json"))
        store.ex("INSERT INTO briefs(brief_id, case_id, name, headcount, workstations, rooms, "
                 "brief_sha256, created_at) VALUES (?,?,?,?,?,?,?,?)",
                 (bid, case_id, (f.get("brief_name") or bid).strip()[:80], b["target_headcount"],
                  b["open_workstations"], json.dumps(b["rooms"], ensure_ascii=False), sha,
                  store.now()))
        if quiere_generar:
            return _launch(case_id, bid)
        return redirect(url_for("case_view", case_id=case_id))

    @app.post("/case/<case_id>/generate")
    @auth.require
    def generate(case_id):
        case_or_404(case_id)
        bid = request.form.get("brief_id") or abort(400)
        bloqueos = intake.blockers_for_generate(case_id)
        if bloqueos:
            return _render_case(case_id, brief_errors={"generate": " ".join(bloqueos)}, code=400)
        return _launch(case_id, bid)

    def _launch(case_id: str, brief_id: str):
        """Última barrera antes de encolar. Si algo llegó hasta acá sin cumplir, no se crea run:
        un run que nace condenado sólo sirve para producir un FAILED que confunde."""
        if store.q1("SELECT brief_id FROM briefs WHERE brief_id=? AND case_id=?",
                    (brief_id, case_id)) is None:
            abort(404)
        bloqueos = intake.blockers_for_generate(case_id)
        if bloqueos:
            return _render_case(case_id, brief_errors={"generate": " ".join(bloqueos)}, code=400)
        run_id = "R_" + uuid.uuid4().hex[:10]
        store.ex("INSERT INTO runs(run_id, case_id, brief_id, status, created_at) "
                 "VALUES (?,?,?,'QUEUED',?)", (run_id, case_id, brief_id, store.now()))
        for a in engine.ALTS:
            store.ex("INSERT OR REPLACE INTO alternatives(run_id, alt, status) "
                     "VALUES (?,?,'GENERATING')", (run_id, a))
        engine.enqueue(run_id)
        return redirect(url_for("run_view", run_id=run_id))

    # ---------- resultados y revisión ---------------------------------------------------------
    @app.get("/run/<run_id>")
    @auth.require
    def run_view(run_id):
        r = store.q1("SELECT * FROM runs WHERE run_id=?", (run_id,))
        if r is None:
            abort(404)
        c = store.q1("SELECT * FROM cases WHERE case_id=?", (r["case_id"],))
        b = store.q1("SELECT * FROM briefs WHERE brief_id=?", (r["brief_id"],))
        alts = []
        for a in store.q("SELECT * FROM alternatives WHERE run_id=? ORDER BY alt", (run_id,)):
            d = dict(a)
            d["metrics"] = store.js(a["metrics"], {})
            d["quality"] = store.js(a["quality"], {})
            d["detail"] = store.js(a["detail"], {})
            d["review"] = store.q1(
                "SELECT * FROM reviews WHERE run_id=? AND alt=? ORDER BY id DESC LIMIT 1",
                (run_id, a["alt"]))
            d["has_plan"] = os.path.exists(_alt_file(r["case_id"], run_id, a["alt"],
                                                     "layout_commercial.png"))
            alts.append(d)
        return render_template("run.html", r=r, c=c, b=b, alts=alts, grades=GRADES,
                               tags=reason_tags(), reviewer=REVIEWER,
                               rooms=store.js(b["rooms"], []) if b else [])

    @app.get("/run/<run_id>/status.json")
    @auth.require
    def run_status(run_id):
        r = store.q1("SELECT * FROM runs WHERE run_id=?", (run_id,))
        if r is None:
            abort(404)
        alts = store.q("SELECT alt, status FROM alternatives WHERE run_id=? ORDER BY alt",
                       (run_id,))
        return jsonify({"run": r["status"],
                        "alts": {a["alt"]: a["status"] for a in alts}})

    def _alt_file(case_id: str, run_id: str, alt: str, name: str) -> str:
        return os.path.join(engine.run_dir(case_id, alt_or_404(alt) and run_id),
                            "alternatives", alt, name)

    @app.get("/run/<run_id>/alt/<alt>/<kind>")
    @auth.require
    def alt_asset(run_id, alt, kind):
        r = store.q1("SELECT case_id FROM runs WHERE run_id=?", (run_id,))
        if r is None:
            abort(404)
        names = {"plan.png": ("layout_commercial.png", "image/png"),
                 "technical.svg": ("layout_technical.svg", "image/svg+xml"),
                 "geometry.png": ("layout_geometry.png", "image/png")}
        if kind not in names:
            abort(404)
        fn, mime = names[kind]
        p = _alt_file(r["case_id"], run_id, alt, fn)
        if not os.path.exists(p):
            abort(404)
        return send_file(p, mimetype=mime)

    @app.post("/run/<run_id>/review")
    @auth.require
    def save_review(run_id):
        r = store.q1("SELECT * FROM runs WHERE run_id=?", (run_id,))
        if r is None:
            abort(404)
        f = request.form
        alt = alt_or_404(f.get("alt", ""))
        grade = f.get("grade")
        if grade not in dict(GRADES):
            abort(400)
        a = store.q1("SELECT * FROM alternatives WHERE run_id=? AND alt=?", (run_id, alt))
        b = store.q1("SELECT brief_sha256 FROM briefs WHERE brief_id=?", (r["brief_id"],))
        valid = set(reason_tags())
        tags = [t for t in f.getlist("tags") if t in valid]
        try:
            minutes = float(f.get("minutes") or 0)
        except ValueError:
            minutes = 0.0
        store.ex("INSERT INTO reviews(case_id, run_id, alt, grade, reason_tags, free_note, "
                 "minutes_spent, reviewer, reviewed_at, layout_sha256, engine_commit, "
                 "brief_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (r["case_id"], run_id, alt, grade, json.dumps(tags, ensure_ascii=False),
                  (f.get("note") or "")[:2000], minutes, REVIEWER, store.now(),
                  a["layout_sha256"] if a else None, r["engine_commit"],
                  b["brief_sha256"] if b else None))
        return redirect(url_for("run_view", run_id=run_id) + f"#alt{alt}")

    @app.post("/run/<run_id>/best")
    @auth.require
    def save_best(run_id):
        if store.q1("SELECT run_id FROM runs WHERE run_id=?", (run_id,)) is None:
            abort(404)
        best = request.form.get("best_alt", "")
        if best not in ("A", "B", "C", "NINGUNA"):
            abort(400)
        store.ex("UPDATE runs SET best_alt=? WHERE run_id=?", (best, run_id))
        return redirect(url_for("run_view", run_id=run_id))

    @app.get("/reviews.json")
    @auth.require
    def reviews_export():
        """Export en el formato del contrato: una lista de HumanLayoutReviewV1."""
        out = []
        for r in store.q("SELECT * FROM reviews ORDER BY reviewed_at"):
            out.append({"contract_version": "human_layout_review_v1", "case_id": r["case_id"],
                        "brief_id": store.q1("SELECT brief_id FROM runs WHERE run_id=?",
                                             (r["run_id"],))["brief_id"],
                        "alternative": r["alt"], "layout_sha256": r["layout_sha256"],
                        "grade": r["grade"], "reason_tags": store.js(r["reason_tags"], []),
                        "free_note": r["free_note"], "reviewer": r["reviewer"],
                        "reviewed_at": r["reviewed_at"], "minutes_spent": r["minutes_spent"],
                        "_engine_commit": r["engine_commit"], "_brief_sha256": r["brief_sha256"],
                        "_run_id": r["run_id"]})
        return jsonify(out)

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "version": APP_VERSION,
                        "cases": store.q1("SELECT COUNT(*) n FROM cases")["n"],
                        "jobs_pending": engine.pending()})

    @app.errorhandler(413)
    def too_big(_):
        return render_template("error.html", back=url_for("library"),
                               msg=f"Archivo demasiado grande (máximo {intake.MAX_UPLOAD_MB} MB "
                                   f"por planta)."), 413
    return app


def _pair(x, y):
    try:
        return [float(x), float(y)] if x not in (None, "") and y not in (None, "") else None
    except (TypeError, ValueError):
        return None


app = None
if os.environ.get("ESCALIMETRO_EAGER", "") == "1":
    app = create_app()
