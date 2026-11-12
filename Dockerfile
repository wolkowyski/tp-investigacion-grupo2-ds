# Demo del Grupo 2 en un contenedor.
# Solo usa la biblioteca estándar de Python (SQLite incluido): no instala nada.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    DB_PATH=/tmp/demo.db

COPY *.py ./

CMD ["python", "main.py"]
