"""API REST que consume la WebApp Spring Boot."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .plano_datos import (FICHERO_DUMP, Conexion, analizar_bbdd, analizar_dependencias, crear_bbdd,
                          directorio_dumps, directorio_dumps_servidor, exportar_bbdd,
                          formar_arboles, generar_prototipo, insertar_datos,
                          listar_registro, ordenar_arboles, parsear_ddl, probar_servidor, progreso_insercion,
                          restaurar_bbdd)

app = FastAPI(title="SQL Analyzer API", version="0.1.0")

# DTOs
# Los DTOs de peticiones son lo que manda Java.

class PeticionDdl(BaseModel):
    ddl: str = Field(max_length=100_000)

# Error con su fila y columna
class ErrorDdlDto(BaseModel):
    mensaje: str
    linea: int | None = None
    columna: int | None = None

# FK con su tabla padre y sus columnas.
class ClaveForaneaDto(BaseModel):
    tabla: str
    columnas: list[str]
    tabla_padre: str
    # Vacío si el DDL no las indica: referencia la PK de la tabla padre.
    columnas_padre: list[str]

# Nivel de Kahn de la Tabla.
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

# Orden de carga de los árboles.
class ArbolOrdenadoDto(BaseModel):
    # Raíz del árbol.
    raiz: str
    nivel: int
    # Raíces de los árboles que deben cargarse antes.
    depende_de: list[str]
    # FK que crean esas dependencias.
    referencias: list[ClaveForaneaDto]

# ValidaciónDdl.
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


class PeticionPrototipo(BaseModel):
    ddl: str = Field(max_length=100_000)
    # Número de filas de cada tabla (el único dato que indica el usuario).
    filas: dict[str, int]

# Información de las columnas
class ColumnaPrototipoDto(BaseModel):
    nombre: str
    tipo: str
    # "tipo" (valor según su tipo), "fk" (valor de la tabla padre) o "auto" (lo rellena PostgreSQL).
    origen: str

# Información de las tablas.
class TablaPrototipoDto(BaseModel):
    tabla: str
    filas: int
    columnas: list[ColumnaPrototipoDto]
    # Primeras filas del prototipo, ya formateadas.
    muestra: list[list[str]]

# PrototipoDatos.
class RespuestaPrototipo(BaseModel):
    valido: bool
    errores: list[ErrorDdlDto]
    # En el orden de Kahn de las tablas (paso 2.1).
    tablas: list[TablaPrototipoDto] = []


# PostgreSQL de otro equipo de la red (paso 9: restaurar la BBDD en él).
class ServidorDto(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    puerto: int = Field(default=5432, ge=1, le=65535)
    usuario: str = Field(min_length=1, max_length=63)
    contrasena: str = Field(default="", max_length=200)


class PeticionCreacion(PeticionPrototipo):
    # Nombre de la base de datos que se va a crear.
    nombre: str = Field(max_length=63)


class TablaCreadaDto(BaseModel):
    tabla: str
    # CREATE TABLE ejecutado.
    sentencia: str

# CreacionBbdd.
class RespuestaCreacion(BaseModel):
    valido: bool
    errores: list[ErrorDdlDto]
    bbdd: str | None = None
    # Esquemas creados (CREATE SCHEMA) antes de las tablas.
    esquemas: list[str] = []
    # En el orden en que se han creado (Kahn).
    tablas: list[TablaCreadaDto] = []


class TablaInsertadaDto(BaseModel):
    tabla: str
    filas: int


# InsercionDatos.
class RespuestaInsercion(BaseModel):
    valido: bool
    errores: list[ErrorDdlDto]
    bbdd: str | None = None
    # En el orden en que se han escrito (Kahn).
    tablas: list[TablaInsertadaDto] = []
    # Tiempo de la generación y la escritura.
    segundos: float = 0.0


# Lo que sabe PostgreSQL de una tabla antes y después del ANALYZE.
class TablaAnalizadaDto(BaseModel):
    tabla: str
    # Filas pedidas en el prototipo.
    filas: int
    # pg_class.reltuples antes (-1: nunca analizada) y después del ANALYZE.
    estimadas_antes: int
    estimadas: int
    # pg_class.relpages.
    paginas: int
    # Columnas con estadísticas en pg_stats.
    columnas: int


# AnalisisBbdd.
class RespuestaAnalisis(BaseModel):
    valido: bool
    errores: list[ErrorDdlDto]
    bbdd: str | None = None
    # En el orden en que se han analizado (Kahn).
    tablas: list[TablaAnalizadaDto] = []
    segundos: float = 0.0


# ExportacionBbdd.
class RespuestaExportacion(BaseModel):
    valido: bool
    errores: list[ErrorDdlDto]
    bbdd: str | None = None
    # Fichero del dump (se descarga con GET /bbdd/dumps/{fichero}) y su tamaño en bytes.
    fichero: str | None = None
    bytes: int = 0
    # Momento del registro en el repositorio.
    registrada: datetime | None = None
    segundos: float = 0.0


# Una BBDD registrada.
class BbddRegistradaDto(BaseModel):
    # «host:puerto» del PostgreSQL de otro equipo donde se ha restaurado (paso 9); vacío = la aplicación.
    servidor: str = ""
    nombre: str
    tablas: int
    total_filas: int
    fichero: str
    bytes: int
    registrada: datetime
    # Si la BBDD sigue existiendo en el servidor. None en los servidores de otros equipos (no se comprueba).
    existe: bool | None = None


def conexion() -> Conexion:
    """Conexión con PostgreSQL (los tests la sustituyen)."""
    return Conexion.desde_entorno()


# Nombres que, para el usuario, son «mi propio equipo». Dentro de Docker significan el contenedor de la API:
# si HOST_LOCAL está definida (docker-compose.yml: host.docker.internal), se cambian por ella.
_LOCALES = {"localhost", "127.0.0.1", "::1"}


def _destino(servidor: ServidorDto, con: Conexion) -> Conexion:
    """Conexión con el PostgreSQL de otro equipo de la red. Se mantienen las BBDD reservadas de la aplicación
    (repositorio) para no usarlas nunca."""
    host = servidor.host.strip()
    if host.lower() in _LOCALES and os.environ.get("HOST_LOCAL"):
        host = os.environ["HOST_LOCAL"] # Traducción de localhost.
    return replace(con, host=host, puerto=servidor.puerto, usuario=servidor.usuario,
                   contrasena=servidor.contrasena, bd_mantenimiento="postgres")


def dumps() -> Path:
    """Directorio donde la API lee los dumps para descargarlos (los tests lo sustituyen)."""
    return directorio_dumps()


def dumps_servidor() -> str:
    """Directorio donde PostgreSQL escribe los dumps, ruta del servidor (los tests lo sustituyen)."""
    return directorio_dumps_servidor()


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
    respuesta, _, _ = _analizar_ddl(peticion.ddl)
    return respuesta


@app.post("/bbdd/prototipo", response_model=RespuestaPrototipo)
def definir_prototipo(peticion: PeticionPrototipo) -> RespuestaPrototipo:
    """Paso 3: el usuario indica el número de filas de cada tabla y se devuelve una muestra.

    La API no guarda nada entre peticiones: el DDL se vuelve a analizar (pasos 1 y 2).
    """
    respuesta, resultado, dependencias = _analizar_ddl(peticion.ddl)
    if not respuesta.valido:
        return RespuestaPrototipo(valido=False, errores=respuesta.errores)
    prototipo = generar_prototipo(resultado.sentencias, dependencias, peticion.filas)
    return RespuestaPrototipo(
        valido=prototipo.valido,
        errores=_errores(prototipo.errores),
        tablas=[TablaPrototipoDto(
            tabla=t.tabla, filas=t.filas,
            columnas=[ColumnaPrototipoDto(nombre=c.nombre, tipo=c.tipo, origen=o) for c, o in zip(t.columnas, t.origenes)],
            muestra=t.muestra) for t in prototipo.tablas],
    )


@app.post("/bbdd/crear", response_model=RespuestaCreacion)
def crear(peticion: PeticionCreacion, con: Conexion = Depends(conexion)) -> RespuestaCreacion:
    """Paso 4: el usuario confirma y se revisa el nombre de la BBDD contra el servidor.
    Paso 5: CREATE DATABASE y CREATE TABLE en el orden de Kahn.

    Antes se vuelven a comprobar el DDL (pasos 1 y 2) y el prototipo (paso 3): la API no guarda nada.
    """
    respuesta, resultado, dependencias = _analizar_ddl(peticion.ddl)
    if not respuesta.valido:
        return RespuestaCreacion(valido=False, errores=respuesta.errores)
    prototipo = generar_prototipo(resultado.sentencias, dependencias, peticion.filas)
    if not prototipo.valido:
        return RespuestaCreacion(valido=False, errores=_errores(prototipo.errores))
    creacion = crear_bbdd(peticion.nombre, resultado.sentencias, dependencias, con)
    return RespuestaCreacion(
        valido=creacion.valido,
        errores=_errores(creacion.errores),
        bbdd=creacion.bbdd,
        esquemas=creacion.esquemas,
        tablas=[TablaCreadaDto(tabla=t.tabla, sentencia=t.sentencia) for t in creacion.tablas],
    )


@app.post("/bbdd/insertar", response_model=RespuestaInsercion)
def insertar(peticion: PeticionCreacion, con: Conexion = Depends(conexion)) -> RespuestaInsercion:
    """Paso 6: genera las tuplas siguiendo el diagrama (árbol a árbol y en profundidad) y las escribe
    tabla a tabla en el orden de Kahn en la BBDD creada en el paso 5.

    Recibe lo mismo que /bbdd/crear. Antes se vuelven a comprobar el DDL y el prototipo.
    """
    respuesta, resultado, dependencias = _analizar_ddl(peticion.ddl)
    if not respuesta.valido:
        return RespuestaInsercion(valido=False, errores=respuesta.errores)
    arboles = formar_arboles(dependencias)
    orden_carga = ordenar_arboles(dependencias, arboles, peticion.ddl)
    insercion = insertar_datos(peticion.nombre, resultado.sentencias, dependencias, arboles, orden_carga,
                               peticion.filas, con)
    return RespuestaInsercion(
        valido=insercion.valido,
        errores=_errores(insercion.errores),
        bbdd=insercion.bbdd,
        tablas=[TablaInsertadaDto(tabla=t.tabla, filas=t.filas) for t in insercion.tablas],
        segundos=insercion.segundos,
    )


# Progreso de una inserción en marcha (reloj de la carga en la WebApp).
class ProgresoInsercionDto(BaseModel):
    # «generando» (tuplas) o «escribiendo» (COPY tabla a tabla).
    fase: str
    # Tabla que se está escribiendo (None mientras se generan las tuplas).
    tabla: str | None = None
    # Filas hechas en la fase actual, de total (las filas de todas las tablas).
    hechas: int
    total: int


@app.get("/bbdd/insertar/progreso/{nombre}", response_model=ProgresoInsercionDto)
def progreso(nombre: str) -> ProgresoInsercionDto:
    """Paso 6: cómo va la inserción en marcha en «nombre». 404 si no hay ninguna (no ha empezado o ya ha
    terminado). Se puede consultar mientras dura POST /bbdd/insertar: FastAPI atiende cada petición en un hilo."""
    p = progreso_insercion(nombre)
    if p is None:
        raise HTTPException(404, f"No hay ninguna inserción en marcha en «{nombre}»")
    return ProgresoInsercionDto(fase=p.fase, tabla=p.tabla, hechas=p.hechas, total=p.total)


@app.post("/bbdd/analizar", response_model=RespuestaAnalisis)
def analizar(peticion: PeticionCreacion, con: Conexion = Depends(conexion)) -> RespuestaAnalisis:
    """Paso 7: ANALYZE de cada tabla en el orden de Kahn para cerrar la carga, de modo que el planificador
    tenga estadísticas reales de los datos insertados en el paso 6.

    Recibe lo mismo que /bbdd/insertar: el DDL da las tablas y las filas, las que debería tener cada una.
    """
    respuesta, _, dependencias = _analizar_ddl(peticion.ddl)
    if not respuesta.valido:
        return RespuestaAnalisis(valido=False, errores=respuesta.errores)
    analisis = analizar_bbdd(peticion.nombre, dependencias, peticion.filas, con)
    return RespuestaAnalisis(
        valido=analisis.valido,
        errores=_errores(analisis.errores),
        bbdd=analisis.bbdd,
        tablas=[TablaAnalizadaDto(tabla=t.tabla, filas=t.filas, estimadas_antes=t.estimadas_antes,
                                  estimadas=t.estimadas, paginas=t.paginas, columnas=t.columnas)
                for t in analisis.tablas],
        segundos=analisis.segundos,
    )


@app.post("/bbdd/exportar", response_model=RespuestaExportacion)
def exportar(peticion: PeticionCreacion, con: Conexion = Depends(conexion),
             directorio: str = Depends(dumps_servidor)) -> RespuestaExportacion:
    """Paso 8: respaldo con COPY (SELECT 1) TO PROGRAM 'pg_dump ... -F c' desde el servidor (8.1) y registro
    como BBDD objetivo en el repositorio (8.2). La carga debe estar cerrada (paso 7). Llega a Windows al
    descargarlo con GET /bbdd/dumps/{fichero}.

    Recibe lo mismo que /bbdd/analizar: el DDL y las filas se guardan en el registro.
    """
    respuesta, _, dependencias = _analizar_ddl(peticion.ddl)
    if not respuesta.valido:
        return RespuestaExportacion(valido=False, errores=respuesta.errores)
    exportacion = exportar_bbdd(peticion.nombre, peticion.ddl, dependencias, peticion.filas, con, directorio)
    return RespuestaExportacion(valido=exportacion.valido, errores=_errores(exportacion.errores),
                                bbdd=exportacion.bbdd, fichero=exportacion.fichero, bytes=exportacion.bytes,
                                registrada=exportacion.registrada, segundos=exportacion.segundos)


@app.get("/bbdd/registro", response_model=list[BbddRegistradaDto])
def registro(con: Conexion = Depends(conexion)) -> list[BbddRegistradaDto]:
    """Paso 8.2: BBDD objetivo registradas, la última primero (las podrá elegir el módulo 2)."""
    try:
        registradas = listar_registro(con)
    except psycopg.Error as e:
        raise HTTPException(503, f"No se ha podido leer el registro: {str(e).strip().splitlines()[-1]}") from e
    return [BbddRegistradaDto(servidor=r.servidor, nombre=r.nombre, tablas=r.tablas, total_filas=r.total_filas,
                              fichero=r.fichero, bytes=r.bytes, registrada=r.registrada, existe=r.existe)
            for r in registradas]


# Resultado de «Probar conexión» con el PostgreSQL de otro equipo.
class RespuestaServidor(BaseModel):
    valido: bool
    errores: list[ErrorDdlDto]
    # «host:puerto» con el que se ha conectado la API.
    servidor: str
    # Versión de PostgreSQL del servidor.
    version: str | None = None


@app.post("/bbdd/servidor/probar", response_model=RespuestaServidor)
def probar(servidor: ServidorDto, con: Conexion = Depends(conexion)) -> RespuestaServidor:
    """Paso 9: comprueba que la API llega al PostgreSQL de otro equipo y que el usuario puede crear BBDD."""
    prueba = probar_servidor(_destino(servidor, con))
    return RespuestaServidor(valido=prueba.valido, errores=_errores(prueba.errores), servidor=prueba.servidor,
                             version=prueba.version)


# Paso 9: restaurar la BBDD en el PostgreSQL de otro equipo.
class PeticionRestauracion(BaseModel):
    # BBDD exportada en el paso 8 y su respaldo (<bbdd>_<AAAAMMDD>_<HHMMSS>.dump).
    nombre: str = Field(max_length=63)
    fichero: str = Field(max_length=100)
    servidor: ServidorDto


class TablaRestauradaDto(BaseModel):
    tabla: str
    filas: int


class RespuestaRestauracion(BaseModel):
    valido: bool
    errores: list[ErrorDdlDto]
    bbdd: str | None = None
    # «host:puerto» del otro servidor y su versión de PostgreSQL.
    servidor: str | None = None
    version: str | None = None
    fichero: str | None = None
    # Filas de cada tabla tras el ANALYZE en el otro servidor.
    tablas: list[TablaRestauradaDto] = []
    segundos: float = 0.0


@app.post("/bbdd/restaurar", response_model=RespuestaRestauracion)
def restaurar(peticion: PeticionRestauracion, con: Conexion = Depends(conexion),
              directorio: Path = Depends(dumps)) -> RespuestaRestauracion:
    """Paso 9: pg_restore --create del respaldo del paso 8 en el PostgreSQL de otro equipo, ANALYZE y registro
    de la copia como BBDD objetivo de ese servidor."""
    # Errores relacionados con el fichero.
    if not FICHERO_DUMP.match(peticion.fichero) or not peticion.fichero.endswith(".dump"):
        return RespuestaRestauracion(valido=False, errores=[ErrorDdlDto(
            mensaje=f"«{peticion.fichero}» no es un respaldo del paso 8 (.dump)")])
    # Restauración de la BBDD.
    r = restaurar_bbdd(peticion.nombre, directorio / peticion.fichero, _destino(peticion.servidor, con), con)
    return RespuestaRestauracion(valido=r.valido, errores=_errores(r.errores), bbdd=r.bbdd, servidor=r.servidor,
                                 version=r.version, fichero=r.fichero,
                                 tablas=[TablaRestauradaDto(tabla=t.tabla, filas=t.filas) for t in r.tablas],
                                 segundos=r.segundos)


@app.get("/bbdd/dumps/{fichero}")
def descargar_dump(fichero: str, directorio: Path = Depends(dumps)) -> FileResponse:
    """Paso 8.1: descarga un dump (formato custom de pg_dump). Solo nombres de dump (nada de rutas)."""
    ruta = directorio / fichero # Dada por el directorio del docker-compose.yml
    if not FICHERO_DUMP.match(fichero) or not ruta.is_file():
        raise HTTPException(404, f"No existe el dump «{fichero}»")
    if not os.access(ruta, os.R_OK):
        raise HTTPException(500, f"La API no tiene permiso para leer el dump «{fichero}»")
    tipo = "application/sql" if fichero.endswith(".sql") else "application/octet-stream"
    return FileResponse(ruta, media_type=tipo, filename=fichero)


def _analizar_ddl(ddl: str):
    """Pasos 1 y 2. Devuelve la respuesta y, si el DDL es válido, el parseo y las dependencias."""
    # Validamos el DDL
    resultado = parsear_ddl(ddl)
    if not resultado.valido:
        return RespuestaDdl(valido=False, tablas=resultado.tablas, errores=_errores(resultado.errores)), None, None

    # Comprobamos que las dependencias sean correctas (FK a tablas definidas y sin ciclos).
    dependencias = analizar_dependencias(resultado.sentencias, ddl)
    if not dependencias.valido:
        return RespuestaDdl(valido=False, tablas=resultado.tablas, errores=_errores(dependencias.errores),
                            claves_foraneas=_fks(dependencias.claves_foraneas)), None, None

    # Formamos los árboles y ordenamos cómo debe ser su carga (sin ciclos entre árboles).
    arboles = formar_arboles(dependencias)
    orden_carga = ordenar_arboles(dependencias, arboles, ddl)
    respuesta = RespuestaDdl(
        valido=orden_carga.valido,
        tablas=resultado.tablas,
        errores=_errores(orden_carga.errores),
        claves_foraneas=_fks(dependencias.claves_foraneas),
        orden=[TablaOrdenadaDto(tabla=o.tabla, nivel=o.nivel) for o in dependencias.orden],
        arboles=_arboles(arboles),
        orden_carga=[ArbolOrdenadoDto(raiz=a.raiz, nivel=a.nivel, depende_de=a.depende_de,
                                      referencias=_fks(a.referencias)) for a in orden_carga.orden],
    )
    return respuesta, resultado, dependencias

# Conversión de objetos internos en en listas de DTOs.

def _arboles(arboles) -> list[ArbolDto]:
    return [ArbolDto(raiz=a.raiz, nodos=[
        NodoArbolDto(tabla=n.tabla, padre=n.padre, nivel=n.nivel,
                     fk_agrupacion=_fks([n.fk_agrupacion])[0] if n.fk_agrupacion else None) # Si el nodo es la raíz --> None.
        for n in a.nodos]) for a in arboles]


def _fks(fks) -> list[ClaveForaneaDto]:
    return [ClaveForaneaDto(tabla=fk.tabla, columnas=list(fk.columnas), tabla_padre=fk.tabla_padre,
                            columnas_padre=list(fk.columnas_padre)) for fk in fks]


def _errores(errores) -> list[ErrorDdlDto]:
    return [ErrorDdlDto(mensaje=e.mensaje, linea=e.linea, columna=e.columna) for e in errores]
