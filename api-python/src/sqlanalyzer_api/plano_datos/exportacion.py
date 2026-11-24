"""Paso 8 del módulo 1: «pg_dump y registro» (en la arquitectura: «Exportación pg_dump» y «Registro de BBDD
objetivo» del plano de datos).

- 8.1. Respaldo: conectados a la BBDD que se respalda, se ejecuta

      COPY (SELECT 1) TO PROGRAM 'pg_dump -U <usuario> -d <bbdd> -F c -f <ruta>'

  El programa lo lanza el propio servidor de PostgreSQL, así que pg_dump siempre es el del servidor (misma
  versión) y la API no necesita instalarlo. Formato custom (``-F c``): binario y comprimido, se restaura con
  ``pg_restore``. Se guarda en el directorio de dumps del servidor (volumen ``dumps``, compartido con la API
  para poder descargarlo) como ``<bbdd>_<AAAAMMDD>_<HHMMSS>.dump``. Solo llega a Windows si el usuario lo
  descarga desde la WebApp.
  Requisitos: el usuario debe ser superusuario (o tener ``pg_execute_server_program``).
- 8.2. Registro: la BBDD queda apuntada como BBDD objetivo en el repositorio de la aplicación
  (``sqlanalyzer_repositorio``, tabla ``bbdd_objetivo``) con su DDL, sus filas y su dump. El plano de
  consultas (módulo 2) podrá elegir entre las BBDD registradas. El repositorio está separado de las BBDD
  objetivo: registrar no modifica la BBDD.

Antes se comprueba que la carga esté cerrada: si una tabla con filas aún no se ha analizado (paso 7),
no se respalda nada. Si el registro falla, se borra el dump para no dejar ficheros sin registrar.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg import sql

from .creacion import Conexion, revisar_nombre
from .ddl import ErrorDdl
from .dependencias import Dependencias
from .estadisticas import _leer
from .insercion import _identificador

# Nombre de los ficheros de dump: <bbdd>_<AAAAMMDD>_<HHMMSS>.dump (también evita rutas como «../x»).
# Se aceptan también los .sql (script) de las exportaciones anteriores, para poder descargarlos.
FICHERO_DUMP = re.compile(r"^[a-z_][a-z0-9_]{0,62}_\d{8}_\d{6}\.(dump|sql)$")

# servidor: «host:puerto» del PostgreSQL de otro equipo donde se ha restaurado la BBDD (paso 9);
# vacío ('') = el servidor de la aplicación.
# Dos servidores pueden tener una BBDD con el mismo nombre: la clave es (servidor, nombre).
_TABLA_REGISTRO = """
    CREATE TABLE IF NOT EXISTS bbdd_objetivo (
        servidor     text NOT NULL DEFAULT '',
        nombre       text NOT NULL,
        ddl          text NOT NULL,
        filas        jsonb NOT NULL,
        tablas       int NOT NULL,
        total_filas  bigint NOT NULL,
        fichero_dump text NOT NULL,
        bytes_dump   bigint NOT NULL,
        registrada   timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (servidor, nombre)
    )
"""
# Nota: las filas estarían en el formato: {"pedidos": 8400, "clientes": 1500, "productos": 320}

# Registros creados antes de que existiera la columna servidor (clave solo «nombre»): se adaptan sin perder filas.
_ADAPTAR_REGISTRO = """
    ALTER TABLE bbdd_objetivo ADD COLUMN IF NOT EXISTS servidor text NOT NULL DEFAULT '';
    DO $$ BEGIN
        IF (SELECT array_length(conkey, 1) FROM pg_constraint
            WHERE conrelid = 'bbdd_objetivo'::regclass AND contype = 'p') = 1 THEN
            ALTER TABLE bbdd_objetivo DROP CONSTRAINT bbdd_objetivo_pkey, ADD PRIMARY KEY (servidor, nombre);
        END IF;
    END $$;
"""



@dataclass(frozen=True)
class Exportacion:
    """Resultado del paso 8."""
    bbdd: str | None = None
    # Nombre del fichero del dump (dentro del directorio de dumps) y su tamaño.
    fichero: str | None = None
    # Tamaño
    bytes: int = 0
    # Momento del registro en el repositorio.
    registrada: datetime | None = None
    segundos: float = 0.0
    errores: list[ErrorDdl] = field(default_factory=list)

    # Si har errores --> FALSE.
    @property
    def valido(self) -> bool:
        return not self.errores


@dataclass(frozen=True)
class BbddRegistrada:
    """Una fila de bbdd_objetivo. Mismos campos que el CREATE TABLE, exceptuando el DDL y el nº de filas."""
    # «host:puerto» del servidor de otro equipo; vacío = el servidor de la aplicación.
    servidor: str
    nombre: str
    tablas: int
    total_filas: int
    fichero: str
    bytes: int
    registrada: datetime
    # Si la BBDD sigue existiendo en el servidor (se puede haber borrado a mano). None en los servidores de
    # otros equipos: no se guarda su contraseña, así que no se puede comprobar.
    existe: bool | None


def directorio_dumps() -> Path:
    """Directorio donde la API lee los dumps para descargarlos: DIRECTORIO_DUMPS o ./dumps en local."""
    return Path(os.environ.get("DIRECTORIO_DUMPS", "dumps"))


def directorio_dumps_servidor() -> str:
    """Directorio donde el servidor de PostgreSQL escribe los dumps (ruta dentro del servidor)."""
    return os.environ.get("DIRECTORIO_DUMPS_SERVIDOR", "/datos/dumps")


def _sin_analizar(c: psycopg.Connection, nombre: str, orden: list[str], filas: dict[str, int]) -> list[ErrorDdl]:
    """La carga está cerrada si las tablas existen y las que tienen filas ya se han analizado (paso 7)."""
    for t in orden:
        leido = _leer(c, _identificador(t))
        # Si no se puede leer --> La tabla no existe.
        if leido is None:
            return [ErrorDdl(f"La tabla «{t}» no existe en «{nombre}»: crea antes la base de datos (paso 5)")]
        # Si la tabla debería de tener filas, pero no se han leido --> Falta ANALYZE.
        if filas.get(t, 0) > 0 and leido[0] < 0:
            return [ErrorDdl(f"La tabla «{t}» de «{nombre}» no está analizada: ejecuta antes ANALYZE (paso 7)")]
    return []


def _en_el_servidor(c: psycopg.Connection, orden: str) -> None:
    """Ejecuta una orden del sistema en el servidor de PostgreSQL: COPY (SELECT 1) TO PROGRAM '...'."""
    c.execute(sql.SQL("COPY (SELECT 1) TO PROGRAM {}").format(sql.Literal(orden)))


def _pg_dump(c: psycopg.Connection, nombre: str, ruta: str, conexion: Conexion) -> None:
    """8.1: pg_dump en formato custom. Si falla, se borra lo que haya escrito: nunca queda un dump a medias.

    PostgreSQL lanza los programas con umask 077 (ficheros solo para el usuario postgres): con umask 022 (solo se quita
    el permiso de escritura) el dump queda legible para la API, que lo descarga desde el volumen compartido.
    """
    r, d = shlex.quote(ruta), shlex.quote(str(Path(ruta).parent.as_posix()))
    _en_el_servidor(c, f"umask 022 && mkdir -p {d} && pg_dump -U {shlex.quote(conexion.usuario)}"
                       f" -d {shlex.quote(nombre)} -F c -f {r} || {{ rm -f {r}; exit 1; }}")
    # Si algo falla, se borra el fichero.


def _adaptar_registro(c: psycopg.Connection) -> None:
    """Crea la tabla del registro si no existe y adapta la de versiones anteriores (columna servidor)."""
    c.execute(_TABLA_REGISTRO)
    c.execute(_ADAPTAR_REGISTRO)


def _registrar(nombre: str, ddl: str, filas: dict[str, int], fichero: str, tamano: int,
               conexion: Conexion, servidor: str = "") -> datetime:
    """8.2: apunta la BBDD en el repositorio (si ya estaba, se actualiza con el último dump).

    ``conexion`` es la del servidor de la aplicación (donde está el repositorio); ``servidor``, el
    «host:puerto» de otro equipo donde se ha restaurado la BBDD (paso 9); vacío = la aplicación."""
    # Conexión a la BBDD de mantenimiento. autocommit=True porque CREATE DATABASE no puede ir en medio de una transacción.
    with conexion.conectar(conexion.bd_mantenimiento, autocommit=True) as c:
        # Crea la BBDD repositorio si no existe
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (conexion.bd_repositorio,)).fetchone():
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(conexion.bd_repositorio)))
    # Conexión a la BBDD repositorio.
    with conexion.conectar(conexion.bd_repositorio) as c:
        _adaptar_registro(c) # Se crea la tabla si no existe ya (o se adapta).
        # Se añade la BBDD que se respalda con sus datos.
        return c.execute("""
            INSERT INTO bbdd_objetivo (servidor, nombre, ddl, filas, tablas, total_filas, fichero_dump, bytes_dump)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (servidor, nombre) DO UPDATE SET ddl = EXCLUDED.ddl, filas = EXCLUDED.filas,
                tablas = EXCLUDED.tablas, total_filas = EXCLUDED.total_filas, fichero_dump = EXCLUDED.fichero_dump,
                bytes_dump = EXCLUDED.bytes_dump, registrada = now()
            RETURNING registrada""", # Devuelve la fecha de registro.
            (servidor, nombre, ddl, json.dumps(filas), len(filas), sum(filas.values()), fichero, tamano)).fetchone()[0]


def _detalle(e: psycopg.Error) -> str:
    """Lanza un mensaje legible de un error de psycopg. 
    Usa diag.message_primary si existe y, si no, la última línea del texto de la excepción.
    """
    diag = getattr(e, "diag", None)
    return diag.message_primary if diag and diag.message_primary else str(e).strip().splitlines()[-1]


def exportar_bbdd(nombre: str, ddl: str, dependencias: Dependencias, filas: dict[str, int],
                  conexion: Conexion, directorio_servidor: str) -> Exportacion:
    """Paso 8: respaldo con pg_dump desde el servidor (8.1) y registro como BBDD objetivo (8.2)."""
    # Validación del nombre.
    errores = revisar_nombre(nombre, conexion)
    if errores:
        return Exportacion(errores=errores)
    orden = [o.tabla for o in dependencias.orden]  # Orden de las tablas
    fichero = f"{nombre}_{datetime.now():%Y%m%d_%H%M%S}.dump" # Nombre del fichero con fecha y hora de la API.
    ruta = f"{directorio_servidor.rstrip('/')}/{fichero}" # Directorio dónde se guardará el fichero.


    inicio = time.perf_counter() # Tiempo de inicio.
    try:
        # Conectados a la BBDD que se respalda.
        with conexion.conectar(nombre, autocommit=True) as c:
            # Se comprueba que la carga (hasta el ANALYZE) está cerrada.
            errores = _sin_analizar(c, nombre, orden, filas)
            if errores:
                return Exportacion(errores=errores)
            # Se intenta lanzar pg_dump. Si falla muestra un mensaje de error con sus detalles.
            try:
                _pg_dump(c, nombre, ruta, conexion)
            except psycopg.Error as e:
                detalle = e.diag.message_detail or _detalle(e)
                return Exportacion(errores=[ErrorDdl(f"pg_dump no ha podido respaldar «{nombre}»: {detalle}")])
            # Se lee el tamaño del dump con pg_stat_file (el fichero está en el servidor).
            tamano = c.execute("SELECT size FROM pg_stat_file(%s)", (ruta,)).fetchone()[0]

            # Registro en el repositorio. Si falla, se borra el dump.
            try:
                registrada = _registrar(nombre, ddl, {t: filas.get(t, 0) for t in orden}, fichero, tamano, conexion)
            except psycopg.Error as e:
                _en_el_servidor(c, f"rm -f {shlex.quote(ruta)}")
                return Exportacion(errores=[ErrorDdl(f"No se ha podido registrar «{nombre}» en «{conexion.bd_repositorio}»:"
                                                     f" {_detalle(e)}. No se ha guardado el dump")])
    # Error de conexión
    except psycopg.OperationalError as e:
        return Exportacion(errores=[ErrorDdl(f"No se ha podido conectar con la base de datos «{nombre}»: {_detalle(e)}")])
    # Si todo va bien, devuelve la exportación.
    return Exportacion(bbdd=nombre, fichero=fichero, bytes=tamano, registrada=registrada,
                       segundos=round(time.perf_counter() - inicio, 2))


def listar_registro(conexion: Conexion) -> list[BbddRegistrada]:
    """BBDD objetivo registradas, la última primero. Vacío si el repositorio aún no existe."""
    # Conexión a la BBDD de mantenimento.
    with conexion.conectar(conexion.bd_mantenimiento) as c:
        # Si no existe la BBDD repositorio devuelve []
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (conexion.bd_repositorio,)).fetchone():
            return []
    # Conexión a la BBDD repositorio.
    with conexion.conectar(conexion.bd_repositorio) as c:
        # Si no exista la BBDD objetivo devuelve []
        if c.execute("SELECT to_regclass('bbdd_objetivo')").fetchone()[0] is None:
            return []
        _adaptar_registro(c) # Registros de versiones anteriores, sin la columna servidor.
        # Lee las filas. Solo se puede comprobar si existen las BBDD del servidor de la aplicación.
        filas = c.execute("""
            SELECT servidor, nombre, tablas, total_filas, fichero_dump, bytes_dump, registrada,
                   CASE WHEN servidor = '' THEN EXISTS (SELECT 1 FROM pg_database d WHERE d.datname = r.nombre) END
            FROM bbdd_objetivo r ORDER BY registrada DESC""").fetchall()
    # Se convierte cada fila en un objeto por posición.
    return [BbddRegistrada(*f) for f in filas]


__all__ = ["BbddRegistrada", "Exportacion", "FICHERO_DUMP", "directorio_dumps", "directorio_dumps_servidor",
           "exportar_bbdd", "listar_registro"]
