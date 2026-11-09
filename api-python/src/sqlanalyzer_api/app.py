"""API REST que consume la WebApp Spring Boot."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .plano_datos import analizar_dependencias, formar_arboles, ordenar_arboles, parsear_ddl

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


class NodoArbolDto(BaseModel):
    tabla: str
    # Tabla de la que cuelga (None en la raíz).
    padre: str | None
    nivel: int
    fk_agrupacion: ClaveForaneaDto | None


class ArbolDto(BaseModel):
    raiz: str
    # Preorden: cada tabla aparece antes que las que cuelgan de ella.
    nodos: list[NodoArbolDto]


class ArbolOrdenadoDto(BaseModel):
    # Raíz del árbol.
    raiz: str
    nivel: int
    # Raíces de los árboles que deben cargarse antes.
    depende_de: list[str]
    # FK que crean esas dependencias.
    referencias: list[ClaveForaneaDto]


class RespuestaDdl(BaseModel):
    valido: bool
    tablas: list[str]
    errores: list[ErrorDdlDto]
    claves_foraneas: list[ClaveForaneaDto] = []
    # Orden topológico de Kahn (paso 2.1): los padres siempre antes que sus hijas.
    orden: list[TablaOrdenadaDto] = []
    # Paso 2.2: árboles de agrupación (cada tabla cuelga de su FK de agrupación).
    arboles: list[ArbolDto] = []
    # Paso 2.3: orden de carga de los árboles (Kahn entre árboles).
    orden_carga: list[ArbolOrdenadoDto] = []


@app.get("/salud")
def salud() -> dict[str, str]:
    """Para saber si la API está levantada."""
    return {"estado": "ok"}


@app.post("/bbdd/ddl", response_model=RespuestaDdl)
def validar_ddl(peticion: PeticionDdl) -> RespuestaDdl:
    """Paso 1: pglast parsea el DDL. Paso 2.1: se leen sus FK y se ordenan las tablas con Kahn.
    Paso 2.2: se elige la FK de agrupación de cada tabla y se forman los árboles.
    Paso 2.3: se ordenan los árboles con Kahn para decidir cuál se carga primero.

    Los ciclos (entre tablas o entre árboles) no se resuelven: se devuelven como error.
    """
    # Validamos el DDL
    ddl = peticion.ddl
    resultado = parsear_ddl(ddl)
    if not resultado.valido:
        return RespuestaDdl(valido=False, tablas=resultado.tablas, errores=_errores(resultado.errores))

    # Comprobamos que las dependencias sean correctas (FK a tablas definidas y sin ciclos).
    dependencias = analizar_dependencias(resultado.sentencias, ddl)
    if not dependencias.valido:
        return RespuestaDdl(valido=False, tablas=resultado.tablas, errores=_errores(dependencias.errores),
                            claves_foraneas=_fks(dependencias.claves_foraneas))

    # Formamos los árboles y ordenamos cómo debe ser su carga (sin ciclos entre árboles).
    arboles = formar_arboles(dependencias)
    orden_carga = ordenar_arboles(dependencias, arboles, ddl)
    return RespuestaDdl(
        valido=orden_carga.valido,
        tablas=resultado.tablas,
        errores=_errores(orden_carga.errores),
        claves_foraneas=_fks(dependencias.claves_foraneas),
        orden=[TablaOrdenadaDto(tabla=o.tabla, nivel=o.nivel) for o in dependencias.orden],
        arboles=_arboles(arboles),
        orden_carga=[ArbolOrdenadoDto(raiz=a.raiz, nivel=a.nivel, depende_de=a.depende_de,
                                      referencias=_fks(a.referencias)) for a in orden_carga.orden],
    )


def _arboles(arboles) -> list[ArbolDto]:
    return [ArbolDto(raiz=a.raiz, nodos=[
        NodoArbolDto(tabla=n.tabla, padre=n.padre, nivel=n.nivel,
                     fk_agrupacion=_fks([n.fk_agrupacion])[0] if n.fk_agrupacion else None)
        for n in a.nodos]) for a in arboles]


def _fks(fks) -> list[ClaveForaneaDto]:
    return [ClaveForaneaDto(tabla=fk.tabla, columnas=list(fk.columnas), tabla_padre=fk.tabla_padre,
                            columnas_padre=list(fk.columnas_padre)) for fk in fks]


def _errores(errores) -> list[ErrorDdlDto]:
    return [ErrorDdlDto(mensaje=e.mensaje, linea=e.linea, columna=e.columna) for e in errores]
