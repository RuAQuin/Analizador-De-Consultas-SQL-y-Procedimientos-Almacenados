"""Pasos 4, 5 y 6 · Creación de la BBDD, carga de datos, claves foráneas y ANALYZE."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import psycopg

from ..config import ConfigPostgres
from .especificacion import EspecificacionBbdd
from .sql import ident
from .validacion import ScriptValidado

log = logging.getLogger(__name__)


class BbddYaExiste(RuntimeError):
    pass


@dataclass
class TablaCargada:
    nombre: str
    tuplas: int
    segundos: float


def crear_bbdd(config: ConfigPostgres, nombre: str, reemplazar: bool = False) -> None:
    # CREATE/DROP DATABASE no pueden ir dentro de una transacción.
    with psycopg.connect(**config.conexion(config.bd_mantenimiento), autocommit=True) as conn:
        if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone():
            if not reemplazar:
                raise BbddYaExiste(f"la base de datos '{nombre}' ya existe")
            log.info("Eliminando la BBDD existente '%s'", nombre)
            conn.execute(f"DROP DATABASE {ident(nombre)} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {ident(nombre)}")


def eliminar_bbdd(config: ConfigPostgres, nombre: str) -> None:
    with psycopg.connect(**config.conexion(config.bd_mantenimiento), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {ident(nombre)} WITH (FORCE)")


def crear_y_cargar_tablas(config: ConfigPostgres, espec: EspecificacionBbdd,
                          validado: ScriptValidado) -> list[TablaCargada]:
    """Crea las tablas, las carga de padres a hijas y añade las FK, todo en una transacción."""
    cargadas: list[TablaCargada] = []
    with psycopg.connect(**config.conexion(espec.nombre)) as conn:
        for nombre in validado.orden:
            conn.execute(validado.tablas[nombre])
        log.info("Tablas creadas: %s", ", ".join(validado.orden))

        if espec.semilla is not None:
            conn.execute("SELECT setseed(%s)", (espec.semilla,))
        for nombre in validado.orden:
            inicio = time.perf_counter()
            if validado.cargas[nombre]:
                conn.execute(validado.cargas[nombre])
            tuplas = conn.execute(f"SELECT count(*) FROM {ident(nombre)}").fetchone()[0]
            cargadas.append(TablaCargada(nombre, tuplas, round(time.perf_counter() - inicio, 3)))
            log.info("Tabla '%s' cargada con %d tuplas", nombre, tuplas)

        for sentencia in validado.claves_foraneas:
            conn.execute(sentencia)
        log.info("Claves foráneas añadidas: %d", len(validado.claves_foraneas))
    return cargadas


def analizar(config: ConfigPostgres, nombre_bbdd: str, tablas: list[str]) -> None:
    """ANALYZE de todas las tablas para que los planes trabajen con estadísticas reales."""
    with psycopg.connect(**config.conexion(nombre_bbdd), autocommit=True) as conn:
        for tabla in tablas:
            conn.execute(f"ANALYZE {ident(tabla)}")
    log.info("ANALYZE ejecutado sobre %d tablas", len(tablas))
