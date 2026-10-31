"""API REST que consume la WebApp Spring Boot."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .plano_datos import analizar_dependencias, parsear_ddl, resolver_ciclos

app = FastAPI(title="SQL Analyzer API", version="0.1.0")


class PeticionDdl(BaseModel):
    ddl: str = Field(max_length=100_000)


class ErrorDdlDto(BaseModel):
    mensaje: str
    linea: int | None = None
    columna: int | None = None


class ClaveForaneaDto(BaseModel):
    tabla: str
    columnas: list[str]
    tabla_padre: str
    # Vacío si el DDL no las indica: referencia la PK de la tabla padre.
    columnas_padre: list[str]


class TablaOrdenadaDto(BaseModel):
    tabla: str
    nivel: int


class TablaIntermediaDto(BaseModel):
    tabla: str
    # FK original que sustituye la tabla intermedia.
    sustituye: ClaveForaneaDto


class RespuestaDdl(BaseModel):
    valido: bool
    tablas: list[str]
    errores: list[ErrorDdlDto]
    claves_foraneas: list[ClaveForaneaDto] = []
    # Orden topológico de Kahn (paso 2.1): los padres siempre antes que sus hijas.
    orden: list[TablaOrdenadaDto] = []
    # Tablas intermedias creadas por el sistema para romper ciclos de FK.
    tablas_intermedias: list[TablaIntermediaDto] = []
    # DDL que se usará en adelante: el del usuario o, si había ciclos, el reescrito.
    ddl_final: str | None = None


@app.get("/salud")
def salud() -> dict[str, str]:
    """Para saber si la API está levantada."""
    return {"estado": "ok"}


@app.post("/bbdd/ddl", response_model=RespuestaDdl)
def validar_ddl(peticion: PeticionDdl) -> RespuestaDdl:
    """Paso 1: pglast parsea el DDL. Paso 2.1: se leen sus FK y se ordenan las tablas con Kahn.

    Si las FK forman un ciclo, el sistema lo rompe con tablas intermedias y vuelve
    a analizar el DDL resultante.
    """
    ddl = peticion.ddl
    resultado = parsear_ddl(ddl)
    if not resultado.valido:
        return RespuestaDdl(valido=False, tablas=resultado.tablas, errores=_errores(resultado.errores))

    dependencias = analizar_dependencias(resultado.sentencias, ddl)
    intermedias = []
    if dependencias.ciclo:
        resolucion = resolver_ciclos(ddl)
        if resolucion.errores:
            return RespuestaDdl(valido=False, tablas=resultado.tablas, errores=_errores(resolucion.errores),
                                claves_foraneas=_fks(dependencias.claves_foraneas))
        ddl, intermedias = resolucion.ddl, resolucion.intermedias
        resultado = parsear_ddl(ddl)
        dependencias = analizar_dependencias(resultado.sentencias, ddl)

    return RespuestaDdl(
        valido=dependencias.valido,
        tablas=resultado.tablas,
        errores=_errores(dependencias.errores),
        claves_foraneas=_fks(dependencias.claves_foraneas),
        orden=[TablaOrdenadaDto(tabla=o.tabla, nivel=o.nivel) for o in dependencias.orden],
        tablas_intermedias=[TablaIntermediaDto(tabla=i.tabla, sustituye=_fks([i.sustituye])[0]) for i in intermedias],
        ddl_final=ddl if dependencias.valido else None,
    )


def _fks(fks) -> list[ClaveForaneaDto]:
    return [ClaveForaneaDto(tabla=fk.tabla, columnas=list(fk.columnas), tabla_padre=fk.tabla_padre,
                            columnas_padre=list(fk.columnas_padre)) for fk in fks]


def _errores(errores) -> list[ErrorDdlDto]:
    return [ErrorDdlDto(mensaje=e.mensaje, linea=e.linea, columna=e.columna) for e in errores]
