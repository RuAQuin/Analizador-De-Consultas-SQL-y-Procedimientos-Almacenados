"""API REST que consume la WebApp Spring Boot."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .plano_datos import parsear_ddl

app = FastAPI(title="SQL Analyzer API", version="0.1.0")


class PeticionDdl(BaseModel):
    ddl: str = Field(max_length=100_000)


class ErrorDdlDto(BaseModel):
    mensaje: str
    linea: int | None = None
    columna: int | None = None


class RespuestaDdl(BaseModel):
    valido: bool
    tablas: list[str]
    errores: list[ErrorDdlDto]


@app.get("/salud")
def salud() -> dict[str, str]:
    """Para saber si la API está levantada."""
    return {"estado": "ok"}


@app.post("/bbdd/ddl", response_model=RespuestaDdl)
def validar_ddl(peticion: PeticionDdl) -> RespuestaDdl:
    """Paso 1 del módulo 1: comprueba que pglast parsea el DDL escrito por el usuario."""
    resultado = parsear_ddl(peticion.ddl)
    return RespuestaDdl(
        valido=resultado.valido,
        tablas=resultado.tablas,
        errores=[ErrorDdlDto(mensaje=e.mensaje, linea=e.linea, columna=e.columna)
                 for e in resultado.errores],
    )
