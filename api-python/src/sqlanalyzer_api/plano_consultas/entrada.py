"""Parte 1 del módulo 2: entrada del SQL y BBDD objetivo sobre la que se analiza.

El análisis estático (pglast) no necesita BBDD. Los EXPLAIN sí: se ejecutan sobre una BBDD objetivo, que solo
puede ser una de las generadas y registradas en el módulo 1 (paso 8) en el servidor de la aplicación. Así la API
nunca analiza las BBDD del sistema (postgres, template0...), su propio repositorio ni otras BBDD del servidor,
aunque alguien la llame sin pasar por la WebApp. Las copias restauradas en otros equipos (paso 9) tampoco: su
contraseña no se guarda, así que la API no se puede conectar a ellas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg

from ..plano_datos.creacion import _NOMBRE_VALIDO, _RESERVADAS, Conexion, _mensaje, _sin_conexion
from ..plano_datos.ddl import ErrorDdl

# Máximo de caracteres del SQL que se analiza (el mismo que el formulario de la WebApp).
MAX_SQL = 50_000


@dataclass(frozen=True)
class Destino:
    """BBDD objetivo comprobada. Sin bbdd: solo se podrá hacer el análisis estático."""
    # Si es None --> No hay BBDD --> Solo análisis estático.
    bbdd: str | None = None
    # Versión de PostgreSQL del servidor (EXPLAIN (GENERIC_PLAN) necesita la 16 o posterior).
    version: str | None = None
    errores: list[ErrorDdl] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.errores


def _registrada(nombre: str, conexion: Conexion) -> bool:
    """La BBDD está en el registro de BBDD objetivo del servidor de la aplicación (paso 8)."""
    # Conexión a la BBDD repositorio.
    with conexion.conectar(conexion.bd_repositorio) as c:
        # Si todavía no se ha exportado ninguna BBDD, la tabla del registro no existe.
        if c.execute("SELECT to_regclass('bbdd_objetivo')").fetchone()[0] is None:
            return False
        # Busca la fila con el nombre que se recibe por parámetro.
        return c.execute("SELECT 1 FROM bbdd_objetivo WHERE servidor = '' AND nombre = %s",
                         (nombre,)).fetchone() is not None


def revisar_destino(nombre: str | None, conexion: Conexion) -> Destino:
    """Comprueba la BBDD objetivo: formato, no reservada, registrada en el módulo 1 y existente en el servidor."""
    # Sin BBDD: solo análisis estático, no hace falta el servidor.
    if not nombre:
        return Destino()
    # Nombre de la BBDD no valido.
    if not _NOMBRE_VALIDO.match(nombre):
        return Destino(errores=[ErrorDdl(f"«{nombre}» no es un nombre de base de datos válido")])
    # Nombre de la BBDD reservada.
    if nombre in _RESERVADAS | {conexion.bd_mantenimiento, conexion.bd_repositorio}:
        return Destino(errores=[ErrorDdl(f"«{nombre}» es una base de datos reservada del servidor: no se analiza")])
    try:
        # Conexión a la BBDD de mantenimiento.
        with conexion.conectar(conexion.bd_mantenimiento) as c:
            # «17.11 (Debian 17.11-1.pgdg13+2)» → «17.11».
            version = c.execute("SELECT current_setting('server_version')").fetchone()[0].split()[0]
            # Mira en pg_database si exista la BBDD pedida.
            existe = c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone() is not None
            # Mira si exista la BBDD repositorio.
            hay_repositorio = c.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                                        (conexion.bd_repositorio,)).fetchone() is not None
        # Solo se llama si el repositorio existe, sino daría error.
        registrada = hay_repositorio and _registrada(nombre, conexion)
    # El servidor no responde (o rechaza la conexión).
    except psycopg.OperationalError as e:
        return Destino(errores=[ErrorDdl(_sin_conexion(conexion, e))])
    # Cualquier otro error.
    except psycopg.Error as e:
        return Destino(errores=[ErrorDdl(f"No se ha podido comprobar «{nombre}»: {_mensaje(e)}")])

    # Si la BBDD no está registrada, se rechaza.
    if not registrada:
        return Destino(errores=[ErrorDdl(f"«{nombre}» no es una BBDD objetivo: solo se analizan las BBDD generadas"
                                         " y exportadas en el módulo 1 (paso 8)")])
    # Si está registrada para yo no existe en el servidor --> Error.
    if not existe:
        return Destino(errores=[ErrorDdl(f"«{nombre}» está en el registro, pero ya no existe en el servidor")])
    return Destino(bbdd=nombre, version=version)


__all__ = ["MAX_SQL", "Destino", "revisar_destino"]
