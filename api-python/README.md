# SQL Analyzer · API Python

API REST (FastAPI) que consume la WebApp Spring Boot. Implementa el Módulo 1
(generación de BBDD) paso a paso según el esquema funcional.

| Paso | Estado |
|------|--------|
| 1. El usuario escribe el DDL y se parsea con pglast | Hecho |
| 2. Árbol de agrupación | Pendiente |
| 3. Prototipo de datos | Pendiente |
| 4. Revisión y confirmación | Pendiente |
| 5. CREATE DATABASE / CREATE TABLE | Pendiente |
| 6. Inserción de datos | Pendiente |
| 7. ANALYZE | Pendiente |
| 8. pg_dump y registro | Pendiente |

## Arrancar

Con Docker (desde la raíz del proyecto):

```bash
docker compose up -d --build --wait   # API en http://localhost:8080, PostgreSQL en localhost:5433
```

En local:

```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e .
uvicorn sqlanalyzer_api.app:app --reload
```

## Endpoints

| Método | Ruta | Qué hace |
|--------|------|----------|
| GET | `/salud` | Comprueba que la API está arrancada |
| POST | `/bbdd/ddl` | Paso 1: parsea el DDL con pglast |

`POST /bbdd/ddl` recibe `{"ddl": "CREATE TABLE ..."}` y siempre responde 200:

```json
{"valido": true, "tablas": ["clientes", "compras"], "errores": []}
{"valido": false, "tablas": [], "errores": [{"mensaje": "Error de sintaxis: syntax error at or near \"NUL\"", "linea": 3, "columna": 19}]}
```

Solo se admiten sentencias `CREATE TABLE`; cualquier otra se devuelve como error
indicando su línea. 

## Tests

```bash
pytest
```
