"""Paso 8 · Registro de la BBDD generada en el repositorio de análisis.

El repositorio es una BBDD propia, separada de las BBDD objetivo, para que los
análisis nunca las modifiquen. Aquí solo se gestiona la entidad ``bbdd``: enlace
de conexión, campos y tuplas de cada tabla, y la ruta del script de pg_dump.
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from ..config import ConfigPostgres
from .ejecucion import TablaCargada
from .especificacion import EspecificacionBbdd
from .sql import ident

log = logging.getLogger(__name__)

_DDL_REGISTRO = """
CREATE TABLE IF NOT EXISTS bbdd (
    id             bigint       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre         varchar(63)  NOT NULL UNIQUE,
    origen         varchar(20)  NOT NULL,   -- GENERADA | IMPORTADA (pg_dump)
    conexion       text         NOT NULL,   -- enlace de conexión, sin contraseña
    especificacion jsonb,                   -- petición original de la WebApp
    tablas         jsonb        NOT NULL,   -- [{nombre, tuplas, columnas: [...]}]
    ruta_dump      text,
    creada_en      timestamptz  NOT NULL DEFAULT now()
)
"""


def _asegurar_repositorio(config: ConfigPostgres) -> None:
    with psycopg.connect(**config.conexion(config.bd_mantenimiento), autocommit=True) as conn:
        existe = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                              (config.bd_repositorio,)).fetchone()
        if not existe:
            conn.execute(f"CREATE DATABASE {ident(config.bd_repositorio)}")
            log.info("Creado el repositorio de análisis '%s'", config.bd_repositorio)


def registrar(config: ConfigPostgres, espec: EspecificacionBbdd,
              cargadas: list[TablaCargada], ruta_dump: Path | None) -> int:
    """Registra (o actualiza, si ya existía con ese nombre) la BBDD y devuelve su id."""
    _asegurar_repositorio(config)
    tuplas = {t.nombre: t.tuplas for t in cargadas}
    tablas = [
        {
            "nombre": t.nombre,
            "tuplas": tuplas.get(t.nombre, 0),
            "columnas": [c.model_dump(exclude_none=True) for c in t.columnas],
        }
        for t in espec.tablas
    ]
    with psycopg.connect(**config.conexion(config.bd_repositorio)) as conn:
        conn.execute(_DDL_REGISTRO)
        fila = conn.execute(
            """
            INSERT INTO bbdd (nombre, origen, conexion, especificacion, tablas, ruta_dump)
            VALUES (%s, 'GENERADA', %s, %s, %s, %s)
            ON CONFLICT (nombre) DO UPDATE SET
                origen = EXCLUDED.origen, conexion = EXCLUDED.conexion,
                especificacion = EXCLUDED.especificacion, tablas = EXCLUDED.tablas,
                ruta_dump = EXCLUDED.ruta_dump, creada_en = now()
            RETURNING id
            """,
            (espec.nombre, config.url(espec.nombre), Jsonb(espec.model_dump(mode="json")),
             Jsonb(tablas), str(ruta_dump) if ruta_dump else None),
        ).fetchone()
    log.info("BBDD '%s' registrada con id %d", espec.nombre, fila[0])
    return fila[0]
