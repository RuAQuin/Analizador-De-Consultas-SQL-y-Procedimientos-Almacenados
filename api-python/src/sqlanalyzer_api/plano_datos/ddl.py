"""Paso 1 del módulo 1: el usuario escribe el DDL y se comprueba que pglast lo parsea.

Solo se admiten sentencias ``CREATE TABLE``: es el DDL de creación de las tablas
del que saldrán el árbol de agrupación y el prototipo de datos en los pasos siguientes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pglast import ast, parse_sql
from pglast.parser import ParseError


@dataclass(frozen=True)
class ErrorDdl:
    mensaje: str
    # Posición del error en el texto (empiezan en 1). None si no se conoce.
    linea: int | None = None
    columna: int | None = None


@dataclass(frozen=True)
class ResultadoDdl:
    tablas: list[str] = field(default_factory=list)
    errores: list[ErrorDdl] = field(default_factory=list)
    # Árbol devuelto por pglast; se reutilizará en los pasos siguientes.
    sentencias: tuple[ast.RawStmt, ...] = ()

    @property
    def valido(self) -> bool:
        return not self.errores


def _linea_columna(texto: str, posicion: int) -> tuple[int, int]:
    """Convierte un desplazamiento (0-based) en línea y columna (1-based).
    Devuelva la fila y columna del caracter objetivo."""
    previo = texto[:max(posicion, 0)]
    linea = previo.count("\n") + 1
    columna = posicion - (previo.rfind("\n") + 1) + 1
    return linea, columna


def _nombre_tabla(relacion: ast.RangeVar) -> str:
    """Devuelve el nombre de la tabla."""
    return f"{relacion.schemaname}.{relacion.relname}" if relacion.schemaname else relacion.relname


def parsear_ddl(ddl: str) -> ResultadoDdl:
    """Parsea el DDL con pglast. Devuelve las tablas definidas o los errores encontrados."""
    if not ddl or not ddl.strip():
        return ResultadoDdl(errores=[ErrorDdl("El DDL está vacío: escribe al menos un CREATE TABLE")])

    try:
        sentencias = parse_sql(ddl)
    except ParseError as e:
        mensaje = f"Error de sintaxis: {e.args[0]}"
        # pglast indica la posición del error contando desde 1.
        if e.location:
            linea, columna = _linea_columna(ddl, e.location - 1)
            return ResultadoDdl(errores=[ErrorDdl(mensaje, linea, columna)])
        return ResultadoDdl(errores=[ErrorDdl(mensaje)])

    if not sentencias:
        return ResultadoDdl(errores=[ErrorDdl("El DDL no contiene sentencias: escribe al menos un CREATE TABLE")])

    tablas: list[str] = []
    errores: list[ErrorDdl] = []
    for raw in sentencias:
        if isinstance(raw.stmt, ast.CreateStmt):
            tablas.append(_nombre_tabla(raw.stmt.relation))
        else:
            linea, columna = _linea_columna(ddl, raw.stmt_location or 0)
            tipo = type(raw.stmt).__name__
            errores.append(ErrorDdl(
                f"Solo se admiten sentencias CREATE TABLE (se ha encontrado {tipo})", linea, columna))

    return ResultadoDdl(tablas=tablas, errores=errores, sentencias=sentencias)
