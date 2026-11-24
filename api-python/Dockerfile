FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Paso 9: la API restaura el respaldo en el PostgreSQL de otro equipo con pg_restore. Debe ser de una
# versión igual o mayor que la del dump: se instala el cliente más reciente del repositorio oficial (PGDG).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates postgresql-common \
 && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
 && apt-get install -y --no-install-recommends postgresql-client \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El código se usa directamente desde src (sin instalarlo como paquete): así cambiar el
# código no obliga a descargar nada y la capa de dependencias queda en caché.
ENV PYTHONPATH=/app/src
COPY src ./src

RUN useradd --create-home api
USER api

EXPOSE 8000
CMD ["uvicorn", "sqlanalyzer_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
