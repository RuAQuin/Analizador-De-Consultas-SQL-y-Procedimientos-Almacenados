"""Paso 5 del módulo 1 (con la revisión y confirmación del paso 4): CREATE DATABASE y CREATE TABLE.

Antes de crear nada se revisa el nombre de la BBDD contra el servidor (que tenga un formato válido,
que no sea reservado y que no exista ya). Después se crea la BBDD y, en una sola transacción, sus
esquemas y sus tablas en el orden de Kahn (paso 2.1). Si falla algún CREATE TABLE se deshace todo
y se borra la BBDD recién creada, para no dejarla a medias.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import psycopg
from pglast import ast
from pglast.stream import RawStream
from psycopg import sql

from .ddl import ErrorDdl, nombre_tabla
from .dependencias import Dependencias

# Mismo formato que pide el formulario de la WebApp (un identificador de PostgreSQL sin comillas).
_NOMBRE_VALIDO = re.compile(r"^[a-z_][a-z0-9_]{0,62}$") # Debe empezar en minúsculas o _ y puede tener 63 caracteres como máximo.
# BBDD del servidor que nunca se deben usar.
_RESERVADAS = {"postgres", "template0", "template1"}


@dataclass(frozen=True)
class Conexion:
    """Datos de conexión con el servidor PostgreSQL donde se crean las BBDD."""
    host: str = "localhost"
    puerto: int = 5433
    usuario: str = "postgres"
    contrasena: str = "postgres"
    # BBDD a la que se conecta para ejecutar CREATE DATABASE / DROP DATABASE (existe para que las herramientas y los clientes tengan un sitio al que conectarse).
    bd_mantenimiento: str = "postgres"
    # BBDD donde la API guardará sus análisis (propia de la aplicación): tampoco se puede usar.
    bd_repositorio: str = "sqlanalyzer_repositorio"

    @classmethod
    def desde_entorno(cls) -> Conexion:
        """Lee las variables PG_* (las define docker-compose.yml). Sin ellas, el PostgreSQL de Docker en local."""
        return cls(
            host=os.environ.get("PG_HOST", cls.host),
            puerto=int(os.environ.get("PG_PUERTO", cls.puerto)),
            usuario=os.environ.get("PG_USUARIO", cls.usuario),
            contrasena=os.environ.get("PG_CONTRASENA", cls.contrasena),
            bd_mantenimiento=os.environ.get("PG_BD_MANTENIMIENTO", cls.bd_mantenimiento),
            bd_repositorio=os.environ.get("PG_BD_REPOSITORIO", cls.bd_repositorio),
        ) # Se devuelve la conexión.

    def conectar(self, bd: str, autocommit: bool = False) -> psycopg.Connection:
        """Abre una conexión psycopg con la base de datos."""
        return psycopg.connect(host=self.host, port=self.puerto, user=self.usuario, password=self.contrasena,
                               dbname=bd, autocommit=autocommit, connect_timeout=5) # Timeout de 5 segundos para no quedarse colgado si el servidor no responde.


@dataclass(frozen=True)
class TablaCreada:
    tabla: str
    # Sentencia ejecutada (regenerada por pglast a partir del DDL del usuario).
    sentencia: str


@dataclass(frozen=True)
class Creacion:
    bbdd: str | None = None # Nombre de la BBDD. Si va mal queda en None y devuelve errores; si va bien devuelve los esquemas y las tablas.
    esquemas: list[str] = field(default_factory=list)
    # En el orden en que se han creado (Kahn).
    tablas: list[TablaCreada] = field(default_factory=list)
    errores: list[ErrorDdl] = field(default_factory=list) #

    # Devuelve TRUE si hay errores.
    @property
    def valido(self) -> bool:
        return not self.errores


class _FalloTabla(Exception):
    """Un CREATE TABLE ha fallado: se guarda la tabla para indicarla en el error."""

    def __init__(self, tabla: str, error: psycopg.Error):
        super().__init__(tabla)
        self.tabla = tabla # Nombre de la tabla.
        self.error = error # Error de la tabla.


def sentencias_creacion(sentencias: tuple[ast.RawStmt, ...], dependencias: Dependencias) -> list[TablaCreada]:
    """CREATE TABLE de cada tabla en el orden de Kahn: los padres siempre antes que sus hijas."""
    # Crea un diccionario nombre_tabla --> nodo CreateStmt a partir de las sentencias parseadas.
    creates = {nombre_tabla(r.stmt.relation): r.stmt for r in sentencias}
    # Devuelve las tablas con su SQL y en el orden de creación segun Kahn.
    return [TablaCreada(o.tabla, RawStream()(creates[o.tabla])) for o in dependencias.orden]


def esquemas_usados(sentencias: tuple[ast.RawStmt, ...]) -> list[str]:
    """Esquemas que aparecen en el DDL (CREATE TABLE ventas.clientes), sin repetir y en orden."""
    # Esquemas que aparecen en el DDL.
    esquemas = [r.stmt.relation.schemaname for r in sentencias if r.stmt.relation.schemaname]
    # Se quitan los esquemas repetidos (dict.fromkeys) y se elimina el "public.".
    return list(dict.fromkeys(e for e in esquemas if e != "public"))


def revisar_nombre(nombre: str, conexion: Conexion) -> list[ErrorDdl]:
    """Paso 4: errores del nombre que no dependen del servidor."""
    # Nombre con formato incorrecto o inexistente.
    if not _NOMBRE_VALIDO.match(nombre or ""):
        return [ErrorDdl(f"El nombre «{nombre}» no es válido: solo minúsculas, números y guion bajo,"
                         " empezando por letra o _ (máximo 63 caracteres)")]
    # Nombre de BBDD reservada.
    if nombre in _RESERVADAS | {conexion.bd_mantenimiento, conexion.bd_repositorio}:
        return [ErrorDdl(f"«{nombre}» es una base de datos reservada del servidor: elige otro nombre")]
    return []


def _mensaje(error: psycopg.Error) -> str:
    """Mensaje de PostgreSQL sin el prefijo ERROR ni el contexto. Formato legible"""
    diag = getattr(error, "diag", None)
    # Si existe, usa diag.message_primary; si no, como ocurre en algunos errores de conexión, se queda con la primera línea de str(error).
    return (diag.message_primary if diag and diag.message_primary else str(error).strip().splitlines()[0])


def crear_bbdd(nombre: str, sentencias: tuple[ast.RawStmt, ...], dependencias: Dependencias,
               conexion: Conexion) -> Creacion:
    """Pasos 4 y 5: revisa el nombre, crea la BBDD y crea sus tablas en el orden de Kahn."""
    # Validación del nombre, si hay errores no se continúa.
    errores = revisar_nombre(nombre, conexion)
    if errores:
        return Creacion(errores=errores)

    # CREATE DATABASE no puede ejecutarse dentro de una transacción: autocommit.
    try:
        with conexion.conectar(conexion.bd_mantenimiento, autocommit=True) as c:
            # Comprobamos que el nombre de la BBDD no exista.
            if c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone():
                return Creacion(errores=[ErrorDdl(f"Ya existe una base de datos «{nombre}» en el servidor:"
                                                  " elige otro nombre")])
            # Se crea la BBDD con el nombre recibido por parámetro.
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
    # Alguien ha creado la BBDD entre la consulta y el CREATE.
    except psycopg.errors.DuplicateDatabase:
        return Creacion(errores=[ErrorDdl(f"Ya existe una base de datos «{nombre}» en el servidor: elige otro nombre")])
    # No se puede conectar con el servidor.
    except psycopg.OperationalError as e:
        return Creacion(errores=[ErrorDdl(f"No se ha podido conectar con PostgreSQL ({conexion.host}:"
                                          f"{conexion.puerto}): {_mensaje(e)}")])
    # Cualquier otro error (por ejemplo, falta de permisos).
    except psycopg.Error as e:
        return Creacion(errores=[ErrorDdl(f"No se ha podido crear la base de datos «{nombre}»: {_mensaje(e)}")])

    # Se abre una conexión a la BBDD, esta vez sin autocommit.
    esquemas = esquemas_usados(sentencias)
    tablas = sentencias_creacion(sentencias, dependencias)
    try:
        # Una sola transacción: al salir del with se confirma (commit), o se deshace si hay una excepción (rollback).
        with conexion.conectar(nombre) as c:
            # Creación de Esquemas
            for esquema in esquemas:
                c.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(esquema)))
            # Creación de Tablas
            for t in tablas:
                try:
                    c.execute(t.sentencia)
                except psycopg.Error as e:
                    raise _FalloTabla(t.tabla, e) from e
    # Fallo del CREATE TABLE
    except _FalloTabla as e:
        _borrar_bbdd(nombre, conexion)
        return Creacion(errores=[ErrorDdl(f"PostgreSQL no ha podido crear la tabla «{e.tabla}»: {_mensaje(e.error)}."
                                          " No se ha creado la base de datos")])
    # Otro error.
    except psycopg.Error as e:
        _borrar_bbdd(nombre, conexion)
        return Creacion(errores=[ErrorDdl(f"No se han podido crear las tablas: {_mensaje(e)}."
                                          " No se ha creado la base de datos")])
    # En caso de error, el rollback no eliminaría la BBDD, por eso en los errores se llama a _borrar_bbdd.
    return Creacion(bbdd=nombre, esquemas=esquemas, tablas=tablas)


def _borrar_bbdd(nombre: str, conexion: Conexion) -> None:
    """Borra la BBDD recién creada si sus tablas no se han podido crear."""
    try:
        with conexion.conectar(conexion.bd_mantenimiento, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nombre)))
    except psycopg.Error:
        pass  # Si no se puede borrar, el error que se muestra es el de la tabla.
