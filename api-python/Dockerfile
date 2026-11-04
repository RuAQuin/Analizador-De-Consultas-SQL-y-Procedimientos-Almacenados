FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

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
