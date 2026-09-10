"""Punto de entrada WSGI. `gunicorn wsgi:app` en el contenedor; `python wsgi.py` en local."""
import os

from webapp.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
