"""Generación del DDL: CREATE TABLE de cada tabla y ALTER TABLE de las claves foráneas.

Las claves foráneas no van dentro del CREATE TABLE: se añaden con ALTER TABLE
una vez cargados los datos, porque así la carga es más rápida (no se comprueba
cada fila contra la tabla padre).
"""

from __future__ import annotations

from .especificacion import EspecificacionBbdd, Tabla
from .sql import ident

_MAX_IDENTIFICADOR = 63


def _nombre_restriccion(*partes: str) -> str:
    return "_".join(partes)[:_MAX_IDENTIFICADOR]


def crear_tabla(tabla: Tabla) -> str:
    pk = tabla.clave_primaria
    pk_compuesta = len(pk) > 1
    lineas = []
    for col in tabla.columnas:
        partes = [ident(col.nombre), col.tipo]
        if col.identidad:
            partes.append("GENERATED ALWAYS AS IDENTITY")
        if col.pk and not pk_compuesta:
            partes.append("PRIMARY KEY")
        elif not col.nulable:
            partes.append("NOT NULL")
        if col.unico and not (col.pk and not pk_compuesta):
            partes.append("UNIQUE")
        lineas.append("    " + " ".join(partes))
    if pk_compuesta:
        columnas = ", ".join(ident(c.nombre) for c in pk)
        lineas.append(f"    CONSTRAINT {ident(_nombre_restriccion(tabla.nombre, 'pkey'))} PRIMARY KEY ({columnas})")
    return f"CREATE TABLE {ident(tabla.nombre)} (\n" + ",\n".join(lineas) + "\n);"


def claves_foraneas(espec: EspecificacionBbdd) -> list[str]:
    sentencias = []
    for tabla in espec.tablas:
        for col in tabla.columnas:
            destino = espec.destino_fk(col)
            if destino is None:
                continue
            padre, referenciada = destino
            nombre = _nombre_restriccion("fk", tabla.nombre, col.nombre)
            sentencias.append(
                f"ALTER TABLE {ident(tabla.nombre)} ADD CONSTRAINT {ident(nombre)} "
                f"FOREIGN KEY ({ident(col.nombre)}) "
                f"REFERENCES {ident(padre.nombre)} ({ident(referenciada.nombre)});"
            )
    return sentencias
