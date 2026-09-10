# E27 — imagen del servicio web interno de ESCALÍMETRO.
#
# Python 3.12 y no 3.13/3.14: es la versión para la que ortools y opencv publican wheels estables.
# Compilar ortools desde fuente en el build de Railway no es una opción razonable.
FROM python:3.12-slim

# tesseract: el pipeline de normalización corre con vision="ocr" para leer cotas y rótulos.
# libgl/libglib: opencv los pide aunque sea la build headless.
# libcairo2: `renderer/side_by_side._svg_to_bgr` rasteriza con cairosvg, y cairosvg carga
#   libcairo.so.2 por cffi. Sin ella devuelve None en silencio (su except es un `pass`) y el
#   `cv2.imwrite` de e07/run.py muere — que es EXACTAMENTE el fallo que E12 documentó en
#   `ai/svg_rasterizer.py`. Se instala la librería en vez de tocar el motor.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr libgl1 libglib2.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    ESCALIMETRO_DATA_DIR=/data \
    PORT=8080

# /data es el VOLUMEN persistente: uploads, cases, briefs, runs y reviews viven acá, nunca en la
# imagen. Un redeploy reemplaza el código y no toca el trabajo de Joaquín.
#
# NO se declara `VOLUME ["/data"]`: Railway rechaza esa instrucción ("docker VOLUME is not
# supported, use Railway Volumes") porque el montaje lo gestiona la plataforma. El `mkdir` alcanza:
# si hay volumen montado en /data lo sombrea, y si no lo hay el directorio existe igual y la app
# arranca (con estado efímero, que es lo correcto para una prueba local del contenedor).
RUN mkdir -p /data
EXPOSE 8080

# Un solo worker a propósito: la cola de generación es un hilo dentro del proceso, y dos workers
# significarían dos motores compitiendo por la misma CPU. Los hilos alcanzan de sobra para la
# navegación mientras una corrida ocupa el suyo.
CMD gunicorn wsgi:app --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 180 --access-logfile -
