"""Paso 7 del módulo 1: «ANALYZE para cerrar la carga».

Tras insertar los datos (paso 6), PostgreSQL todavía no sabe cuántas filas tiene cada tabla ni cómo se
reparten sus valores: hasta que no se analiza, ``pg_class.reltuples`` vale -1 y ``pg_stats`` está vacío.
El planificador usaría estimaciones por defecto y los EXPLAIN del módulo 2 darían planes engañosos
(una de las patologías del esquema funcional: «Rows estimados muy distintos del real → Estadísticas
desactualizadas. Se debe aplicar ANALYZE»).

- Se ejecuta ``ANALYZE`` tabla a tabla en el orden de Kahn (paso 2.1), solo sobre las tablas del DDL
  (no sobre los catálogos del sistema).
- Antes se comprueba que los datos estén insertados: si una tabla debería tener filas y está vacía,
  no se analiza nada (el paso 6 aún no se ha hecho).
- De cada tabla se devuelve lo que sabe PostgreSQL antes y después: filas estimadas (``reltuples``),
  páginas (``relpages``) y columnas con estadísticas (``pg_stats``).
- ANALYZE no cambia los datos, así que se puede repetir sin problema.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import psycopg
from psycopg import sql

from .creacion import Conexion, revisar_nombre
from .ddl import ErrorDdl
from .dependencias import Dependencias
from .insercion import _identificador


@dataclass(frozen=True)
class TablaAnalizada:
    """Lo que sabe PostgreSQL de una tabla antes y después del ANALYZE."""
    tabla: str
    # Filas que se han pedido en el prototipo (e insertado en el paso 6).
    filas: int
    # pg_class.reltuples antes del ANALYZE: -1 si nunca se ha analizado.
    estimadas_antes: int
    # pg_class.reltuples después: las filas que el planificador cree que hay.
    estimadas: int
    # pg_class.relpages: páginas de 8 kB que ocupa la tabla.
    paginas: int
    # Columnas con estadísticas en pg_stats (valores más comunes, histograma, n_distinct...).
    columnas: int


@dataclass(frozen=True)
class Analisis:
    bbdd: str | None = None # None si ha habido algún error.
    # En el orden en que se han analizado (Kahn).
    tablas: list[TablaAnalizada] = field(default_factory=list)
    # Duracióm total del Análisis.
    segundos: float = 0.0
    errores: list[ErrorDdl] = field(default_factory=list)

    # Si no hay errores --> True.
    @property
    def valido(self) -> bool:
        return not self.errores


# Estadísticas que guarda PostgreSQL de una tabla (NULL si la tabla no existe).
# c.reltules --> Filas estimadas; c.relpages --> Las páginas de 8 kB cada una.
# Subconsulta --> Cuántas columnas tienen estadísticas.
_ESTADISTICAS = """
    SELECT c.reltuples::bigint, c.relpages,
           (SELECT count(*) FROM pg_stats s WHERE s.schemaname = n.nspname AND s.tablename = c.relname)
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.oid = to_regclass(%s)
"""
# Se utiliza to_regclass para que en caso de que no exista la tabla se devuelva NULL y no error.
# Nos ayudará a la identificación de errores y a limpiar el log.


def _leer(c: psycopg.Connection, tabla: sql.Identifier) -> tuple[int, int, int] | None:
    """(filas estimadas, páginas, columnas con estadísticas) de la tabla, o None si no existe."""
    return c.execute(_ESTADISTICAS, (tabla.as_string(c),)).fetchone() # Se respetan mayusculas y caracteres especiales.


def analizar_bbdd(nombre: str, dependencias: Dependencias, filas: dict[str, int],
                  conexion: Conexion) -> Analisis:
    """Paso 7: ANALYZE de cada tabla del DDL, en el orden de Kahn, en la BBDD con los datos insertados."""
    # Error en el nombre de la BBDD.
    errores = revisar_nombre(nombre, conexion)
    if errores:
        return Analisis(errores=errores)
    # Orden de Kahn de las tablas.
    orden = [o.tabla for o in dependencias.orden]

    inicio = time.perf_counter() # Tiempo de inicio.
    try:
        # Autocommit: cada ANALYZE se confirma al momento y sus estadísticas se pueden leer justo después.
        with conexion.conectar(nombre, autocommit=True) as c:
            # Estadísticas de antes del ANALYZE.
            antes: dict[str, tuple[int, int, int]] = {}
            for t in orden:
                tabla = _identificador(t)
                leido = _leer(c, tabla)
                # Tabla no existe.
                if leido is None:
                    return Analisis(errores=[ErrorDdl(
                        f"La tabla «{t}» no existe en «{nombre}»: crea antes la base de datos (paso 5)")])
                # Se comprueba la carga con la primera fila de tabla.
                vacia = not c.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(tabla)).fetchone()[0]
                # Si debería tener filas y está vacía, los datos aún no se han insertado.
                if filas.get(t, 0) > 0 and vacia:
                    return Analisis(errores=[ErrorDdl(
                        f"La tabla «{t}» de «{nombre}» está vacía: inserta antes los datos (paso 6)")])
                # Se guardan las estadísticas en el diccionario 'antes'.
                antes[t] = leido
                # Cualquier error supondría no analizar nada. Principio de Atomicidad --> Todo o nada.

            tablas = []
            # Para cada tabla se ejecuta ANALYZE.
            for t in orden:
                tabla = _identificador(t)
                c.execute(sql.SQL("ANALYZE {}").format(tabla))
                estimadas, paginas, columnas = _leer(c, tabla)
                # TablaAnalizada con los datos de antes y después (AUTOCOMMIT).
                tablas.append(TablaAnalizada(t, filas.get(t, 0), antes[t][0], estimadas, paginas, columnas))
    # Problemas de conexión.
    except psycopg.OperationalError as e:
        diag = getattr(e, "diag", None)
        detalle = diag.message_primary if diag and diag.message_primary else str(e).strip().splitlines()[-1]
        return Analisis(errores=[ErrorDdl(f"No se ha podido conectar con la base de datos «{nombre}»: {detalle}")])
    # Cualquier otro fallo de PostgreSQL durante el ANALYZE.
    except psycopg.Error as e:
        return Analisis(errores=[ErrorDdl(f"PostgreSQL no ha podido ejecutar ANALYZE: {e.diag.message_primary or e}")])
    # Si todo va bien, se devuelve el análisis.
    return Analisis(bbdd=nombre, tablas=tablas, segundos=round(time.perf_counter() - inicio, 2))


__all__ = ["Analisis", "TablaAnalizada", "analizar_bbdd"]
