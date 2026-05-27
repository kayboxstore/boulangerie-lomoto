FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV BOULANGERIE_APPDATA_DIR=/data

WORKDIR /app

COPY cloud-run/requirements-cloud.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY boulangerie_app ./boulangerie_app
COPY serveur_central.py ./serveur_central.py

EXPOSE 8080

CMD python serveur_central.py --host 0.0.0.0 --port ${PORT:-8080} --data-dir "${BOULANGERIE_APPDATA_DIR}"
