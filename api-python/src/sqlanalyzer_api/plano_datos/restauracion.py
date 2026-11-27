"""Paso 9 del módulo 1 (opcional): restaurar la BBDD en el PostgreSQL de otro equipo de la red.

La BBDD se genera siempre en el servidor de la aplicación (pasos 1 a 8). Para llevarla a otro servidor se
aprovecha el respaldo del paso 8:

- 9.1. La API ejecuta ``pg_restore --create`` con ese ``.dump`` contra el otro servidor (``postgresql-client``
  instalado en su imagen). ``--no-owner --no-privileges``: los objetos pasan a ser del usuario con el que se
  conecta (en el dump son de ``postgres``, que puede no existir o no ser ese usuario). ``--exit-on-error``:
  al primer error se para y se borra lo restaurado, para no dejar la BBDD a medias. La contraseña va en
  ``PGPASSWORD`` (no en la orden, que se podría ver con ``ps``).
- 9.2. ``ANALYZE``: el dump no lleva las estadísticas del planificador (paso 7), así que se recalculan en el
  otro servidor.
- 9.3. Registro: la copia queda apuntada en el repositorio de la aplicación como BBDD objetivo de ese servidor
  (misma fila que la del paso 8, con ``servidor`` = «host:puerto»).

Requisitos del otro servidor: aceptar conexiones del equipo de la API (``listen_addresses``, ``pg_hba.conf``,
firewall), un usuario con ``CREATEDB`` y una versión igual o mayor que la del servidor de la aplicación
(restaurar en una versión anterior no está garantizado).
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from .creacion import Conexion, _borrar_bbdd, _mensaje, _sin_conexion, revisar_nombre
from .ddl import ErrorDdl

# Tiempo máximo de pg_restore.
_ESPERA_PG_RESTORE = 600


@dataclass(frozen=True)
class TablaRestaurada:
    # Nombre (esquema.tabla)
    tabla: str
    # Filas tras el ANALYZE del otro servidor (reltuples).
    filas: int


@dataclass(frozen=True)
class Restauracion:
    """Resultado del paso 9."""
    bbdd: str | None = None
    # «host:puerto» del otro servidor.
    servidor: str | None = None
    # Versión de PostgreSQL.
    version: str | None = None
    # Fichero .dump
    fichero: str | None = None
    # Lista de tablas.
    tablas: list[TablaRestaurada] = field(default_factory=list)
    # Segundos que ha tardado en hacer la restauración
    segundos: float = 0.0
    # Lista de errores
    errores: list[ErrorDdl] = field(default_factory=list)

    # True cuándo no hay errores.
    @property
    def valido(self) -> bool:
        return not self.errores


class _FalloRestauracion(Exception):
    """pg_restore ha fallado: el mensaje dice por qué."""


def _pg_restore(fichero: Path, destino: Conexion) -> None:
    """9.1: pg_restore --create del dump en el otro servidor (se conecta a su BBDD de mantenimiento)."""
    orden = ["pg_restore", "-h", destino.host, "-p", str(destino.puerto), "-U", destino.usuario,
             "-d", destino.bd_mantenimiento, "--create", "--no-owner", "--no-privileges", "--exit-on-error",
             str(fichero)] # Ej: pg_restore -h 192.168.1.50 -p 5432 -U admin -d postgres --create --no-owner --no-privileges --exit-on-error /datos/respaldos/tienda.dump
            # --create --> Crea la BBDD con el nombre que viene en el dump.
            # --no-owner --no-privileges --> Hace que los objetos pasen a ser del usuario que se conecta.
            # --exit-on-error --> Detiene la restauración en el primer error.

    # Contraseña --> Es una variable de entorno y el timeout máximo para evitar que se quede colgado.
    entorno = {**os.environ, "PGPASSWORD": destino.contrasena, "PGCONNECT_TIMEOUT": "5"} 
    try:
        r = subprocess.run(orden, env=entorno, capture_output=True, text=True, timeout=_ESPERA_PG_RESTORE)
    # pg_restore no instalado.
    except FileNotFoundError as e:
        raise _FalloRestauracion("pg_restore no está instalado en la API (postgresql-client)") from e
    # Tiempo máximo superado.
    except subprocess.TimeoutExpired as e:
        raise _FalloRestauracion(f"ha tardado más de {_ESPERA_PG_RESTORE} s") from e
    # Código de salida != 0.
    if r.returncode != 0:
        # pg_restore escribe «pg_restore: error: ...»: se deja solo el mensaje (las líneas «detail:» incluidas).
        lineas = [l.removeprefix("pg_restore: ").removeprefix("error: ") for l in r.stderr.strip().splitlines()
                  if not l.startswith("pg_restore: warning:")]
        raise _FalloRestauracion(" ".join(lineas) or f"ha terminado con el código {r.returncode}")


def _analizar(nombre: str, destino: Conexion) -> list[TablaRestaurada]:
    """9.2: ANALYZE de toda la BBDD restaurada y filas de cada tabla según el planificador."""
    with destino.conectar(nombre, autocommit=True) as c:
        c.execute("ANALYZE") # El dump no las incluye.
        filas = c.execute("""
            SELECT CASE WHEN n.nspname = 'public' THEN c.relname ELSE n.nspname || '.' || c.relname END,
                   greatest(c.reltuples, 0)::bigint
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
              AND n.nspname NOT LIKE 'pg_toast%'
            ORDER BY 1""").fetchall()
            # Se evita el -1 a las tablas que Postgre nunca ha analizado con greatest(c.reltuples, 0).
            # Sin analizar los esquemas del sistema ('pg_catalog', etc...).
    return [TablaRestaurada(t, f) for t, f in filas]


def _registrar_copia(nombre: str, fichero: str, servidor: str, repositorio: Conexion) -> bool:
    """9.3: copia la fila del paso 8 (servidor de la aplicación) con el servidor de destino. False si la BBDD no
    está registrada (no se ha exportado en el paso 8)."""
    with repositorio.conectar(repositorio.bd_repositorio) as c:
        fila = c.execute("""
            INSERT INTO bbdd_objetivo (servidor, nombre, ddl, filas, tablas, total_filas, fichero_dump, bytes_dump)
            SELECT %s, nombre, ddl, filas, tablas, total_filas, fichero_dump, bytes_dump
            FROM bbdd_objetivo WHERE servidor = '' AND nombre = %s AND fichero_dump = %s
            ON CONFLICT (servidor, nombre) DO UPDATE SET ddl = EXCLUDED.ddl, filas = EXCLUDED.filas,
                tablas = EXCLUDED.tablas, total_filas = EXCLUDED.total_filas, fichero_dump = EXCLUDED.fichero_dump,
                bytes_dump = EXCLUDED.bytes_dump, registrada = now()
            RETURNING 1""", (servidor, nombre, fichero)).fetchone()
            # Se modifica el nuevo servidor y la fecha registrada de la BBDD.
    return fila is not None


def _registrada(nombre: str, fichero: str, repositorio: Conexion) -> bool:
    """El dump es el registrado en el paso 8 para esa BBDD (en el servidor de la aplicación)."""
    try:
        with repositorio.conectar(repositorio.bd_repositorio) as c:
            # Comprobación de que exista la BBDD objetivo.
            if c.execute("SELECT to_regclass('bbdd_objetivo')").fetchone()[0] is None:
                return False
            # Existe --> Busca la fila del servidor.
            return c.execute("SELECT 1 FROM bbdd_objetivo WHERE servidor = '' AND nombre = %s AND fichero_dump = %s",
                             (nombre, fichero)).fetchone() is not None
    # No se ha podido conectar con el repositorio.
    except psycopg.OperationalError:
        return False


def restaurar_bbdd(nombre: str, fichero: Path, destino: Conexion, repositorio: Conexion) -> Restauracion:
    """Paso 9: restaura el dump del paso 8 en el PostgreSQL de otro equipo, lo analiza y lo registra."""
    errores = revisar_nombre(nombre, destino)
    # ¿Nombre válido?
    if errores:
        return Restauracion(errores=errores)
    # Fichero existe?
    if not fichero.is_file():
        return Restauracion(errores=[ErrorDdl(f"No existe el respaldo «{fichero.name}»: exporta antes la base de datos (paso 8)")])
    # ¿BBDD registrada?
    if not _registrada(nombre, fichero.name, repositorio):
        return Restauracion(errores=[ErrorDdl(f"«{fichero.name}» no es el respaldo registrado de «{nombre}»:"
                                              " exporta antes la base de datos (paso 8)")])

    inicio = time.perf_counter()
    # El otro servidor debe responder, dejar crear BBDD y no tener ya una con ese nombre (--create la crea).
    try:
        with destino.conectar(destino.bd_mantenimiento, autocommit=True) as c:
            version = c.execute("SELECT current_setting('server_version')").fetchone()[0]
            if c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone():
                return Restauracion(errores=[ErrorDdl(f"Ya existe una base de datos «{nombre}» en {destino.servidor}:"
                                                      " bórrala antes o restaura en otro servidor")])
    # Error de conexión.
    except psycopg.OperationalError as e:
        return Restauracion(errores=[ErrorDdl(_sin_conexion(destino, e))])

    try:
        # Restauración.
        _pg_restore(fichero, destino)
    # Error --> Se borra.
    except _FalloRestauracion as e:
        # Se borra lo que haya creado a medias (antes se ha comprobado que no existía).
        _borrar_bbdd(nombre, destino)
        return Restauracion(errores=[ErrorDdl(f"pg_restore no ha podido restaurar «{nombre}» en {destino.servidor}: {e}."
                                              " No se ha dejado nada en ese servidor")])
    try:
        # Análisis.
        tablas = _analizar(nombre, destino)
    # Error --> BBDD restaurada pero sin ANALYZE.
    except psycopg.Error as e:
        return Restauracion(errores=[ErrorDdl(f"Se ha restaurado «{nombre}» en {destino.servidor}, pero el ANALYZE ha"
                                              f" fallado: {_mensaje(e)}")])
    try:
        # Registro
        _registrar_copia(nombre, fichero.name, destino.servidor, repositorio)
    # Error --> BBDD restaurada pero sin registrar.
    except psycopg.Error as e:
        return Restauracion(errores=[ErrorDdl(f"Se ha restaurado «{nombre}» en {destino.servidor}, pero no se ha podido"
                                              f" registrar en «{repositorio.bd_repositorio}»: {_mensaje(e)}")])
    # Resultado de la restauración con el tiempo transcurrido.
    return Restauracion(bbdd=nombre, servidor=destino.servidor, version=version, fichero=fichero.name, tablas=tablas,
                        segundos=round(time.perf_counter() - inicio, 2))


__all__ = ["Restauracion", "TablaRestaurada", "restaurar_bbdd"]
