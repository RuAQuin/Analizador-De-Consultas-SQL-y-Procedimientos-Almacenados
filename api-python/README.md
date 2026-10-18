# SQL Analyzer · API Python

De momento solo incluye el **Módulo 1 del plano de datos: generación de BBDD**. 
La API REST, los workers asíncronos y el plano de consultas aún no están implementados.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
pip install -e .
```

## Configuración (variables de entorno)

| Variable              | Por defecto               | Uso                                          |
|-----------------------|---------------------------|----------------------------------------------|
| `PG_HOST`             | `localhost`               | PostgreSQL objetivo                          |
| `PG_PUERTO`           | `5432`                    |                                              |
| `PG_USUARIO`          | `postgres`                | Necesita permiso `CREATEDB`                  |
| `PG_CONTRASENA`       | *(vacía)*                 |                                              |
| `PG_BD_MANTENIMIENTO` | `postgres`                | Desde donde se lanza `CREATE DATABASE`       |
| `PG_BD_REPOSITORIO`   | `sqlanalyzer_repositorio` | Repositorio de análisis (se crea si no existe) |
| `PG_DUMP`             | `pg_dump`                 | Ruta de `pg_dump` si no está en el `PATH`    |
| `DIRECTORIO_DUMPS`    | `dumps`                   | Donde se guardan los scripts exportados      |

## Uso

```bash
# Solo validar (pasos 1-3): no conecta a PostgreSQL y muestra el script SQL ordenado
python -m sqlanalyzer_api.plano_datos ejemplos/compras.json --validar

# Generar la BBDD completa (pasos 1-8)
python -m sqlanalyzer_api.plano_datos ejemplos/compras.json [--reemplazar] [--sin-exportar] [--sin-registrar]
```

Desde código: `generar_bbdd(EspecificacionBbdd.model_validate(datos), ConfigPostgres.desde_entorno())`.

Códigos de salida: `0` correcto, `1` especificación no válida, `2` fallo al ejecutar
(en ese caso la BBDD a medio crear se elimina).

## Pasos del Módulo 1

| Paso | Módulo | Qué hace |
|------|--------|----------|
| 1. Especificación | `especificacion.py` | Modelo JSON: nombre, tablas, columnas (tipo, nulabilidad, PK, FK, UNQ), nº de tuplas y distribución de valores |
| 2. Validación | `validacion.py`, `sql.py` | Tipos interpretados con pglast, toda FK apunta a otra tabla existente y a una columna PK/UNQ de tipo compatible, y el DDL generado se pasa por `pglast.parse_sql` antes de ejecutarlo. Devuelve todos los errores juntos |
| 3. Ordenación | `ordenacion.py` | Orden topológico por FK (padres → hijas); detecta ciclos |
| 4. Generación | `ddl.py`, `ejecucion.py` | `CREATE DATABASE` y `CREATE TABLE` (con PK y UNQ, sin FK) |
| 5. Inserción | `datos.py`, `ejecucion.py` | Los INSERT recibidos o un `INSERT ... SELECT ... generate_series` aleatorio por tabla; las FK se añaden con `ALTER TABLE` al terminar la carga |
| 6. Análisis | `ejecucion.py` | `ANALYZE` de todas las tablas |
| 7. Exportación | `exportacion.py` | `pg_dump` en SQL plano (estructura + datos) |
| 8. Registro | `registro.py` | Alta en la tabla `bbdd` del repositorio de análisis |

`generador.py` encadena los pasos.

## Especificación

```json
{
  "nombre": "tienda",
  "semilla": 0.42,
  "tablas": [
    {
      "nombre": "b",
      "tuplas": 2000000,
      "columnas": [
        {"nombre": "id",         "tipo": "bigint", "identidad": true, "pk": true},
        {"nombre": "cliente_id", "tipo": "integer", "fk": {"tabla": "a", "columna": "id"}},
        {"nombre": "importe",    "tipo": "numeric(12,2)", "minimo": 5, "maximo": 1000},
        {"nombre": "estado",     "tipo": "varchar(20)", "distribucion": [
          {"valor": "ENTREGADO", "porcentaje": 85}, {"valor": "ENVIADO", "porcentaje": 15}
        ]}
      ]
    }
  ]
}
```

Ejemplo completo (el del esquema funcional): [ejemplos/compras.json](ejemplos/compras.json).

**Tabla:** `nombre`, `tuplas`, `columnas` y, opcionalmente, `inserts` (SQL con
sentencias `INSERT` dirigidas solo a esa tabla, que sustituyen a la generación aleatoria).

**Columna:**

| Campo | Descripción |
|-------|-------------|
| `nombre`, `tipo` | Tipos admitidos: `smallint`, `integer`, `bigint`, `numeric(p,s)`, `real`, `double precision`, `boolean`, `date`, `timestamp`, `timestamptz`, `varchar(n)`, `char(n)`, `text`, `uuid` |
| `nulable` | `false` por defecto |
| `pk`, `unico` | PK (puede ser compuesta) y UNQ. Sus valores se generan a partir del nº de tupla, por lo que no se repiten |
| `identidad` | `GENERATED ALWAYS AS IDENTITY` (solo tipos enteros) |
| `fk` | `{"tabla": ..., "columna": ...}`; si se omite `columna`, se usa la PK de la tabla padre. Debe ser otra tabla |
| `minimo`, `maximo` | Rango de los valores aleatorios (números o fechas `AAAA-MM-DD`) |
| `porcentaje_nulos` | % de NULL (requiere `nulable`) |
| `distribucion` | Lista de `{valor, porcentaje}`; si no suma 100 %, el resto toma valores aleatorios |

`semilla` (de -1 a 1) hace la carga reproducible (`setseed`).

## Tests

```bash
pytest
```

`test_generacion_bbdd_postgres.py` genera una BBDD real y solo se ejecuta si está
definida `PG_CONTRASENA` (puede estar vacía si el servidor usa `trust`).
