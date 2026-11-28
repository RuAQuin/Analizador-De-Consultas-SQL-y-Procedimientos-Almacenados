"""Módulo 2, parte 1: entrada del SQL y BBDD objetivo (POST /analisis).

Los tests con PostgreSQL crean un repositorio propio «test_repo_...» con el registro de BBDD objetivo y una BBDD
«test_...», y los borran al terminar. Si PostgreSQL no está arrancado (docker compose up -d), se saltan.
"""

import dataclasses
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app, conexion
from sqlanalyzer_api.plano_consultas import revisar_destino
from sqlanalyzer_api.plano_datos import Conexion
from sqlanalyzer_api.plano_datos.exportacion import _TABLA_REGISTRO

cliente = TestClient(app)
# Puerto 1: ahí no escucha ningún PostgreSQL.
SIN_SERVIDOR = Conexion(host="127.0.0.1", puerto=1)


def analizar(cuerpo, con=SIN_SERVIDOR):
    app.dependency_overrides[conexion] = lambda: con
    try:
        return cliente.post("/analisis", json=cuerpo)
    finally:
        app.dependency_overrides.clear()


# --- Sin servidor ---

def test_sin_bbdd_no_hace_falta_el_servidor():
    r = analizar({"sql": "SELECT 1", "tipo": "CONSULTA"})
    assert r.status_code == 200
    assert r.json() == {"valido": True, "errores": [], "tipo": "CONSULTA", "bbdd": None, "version": None}


def test_bbdd_vacia_es_sin_bbdd():
    assert analizar({"sql": "SELECT 1", "bbdd": ""}).json()["valido"] is True


def test_el_tipo_se_devuelve():
    assert analizar({"sql": "CALL p()", "tipo": "PROCEDIMIENTO"}).json()["tipo"] == "PROCEDIMIENTO"


@pytest.mark.parametrize("cuerpo", [
    {"sql": ""},                                     # SQL vacío
    {"sql": "x" * 50_001},                           # demasiado largo
    {"sql": "SELECT 1", "tipo": "OTRO"},             # tipo desconocido
    {"sql": "SELECT 1", "bbdd": "x" * 64},           # nombre demasiado largo
])
def test_peticiones_invalidas(cuerpo):
    assert analizar(cuerpo).status_code == 422


@pytest.mark.parametrize("nombre", ["Mayusculas", "con-guion", "../x"])
def test_nombre_no_valido(nombre):
    r = analizar({"sql": "SELECT 1", "bbdd": nombre}).json()
    assert r["valido"] is False and "no es un nombre de base de datos válido" in r["errores"][0]["mensaje"]


@pytest.mark.parametrize("nombre", ["postgres", "template0", "template1", "sqlanalyzer_repositorio"])
def test_bbdd_reservadas(nombre):
    r = analizar({"sql": "SELECT 1", "bbdd": nombre}).json()
    assert r["valido"] is False and "reservada" in r["errores"][0]["mensaje"]


def test_servidor_que_no_responde():
    destino = revisar_destino("tienda", SIN_SERVIDOR)
    assert not destino.valido and "No se ha podido conectar con PostgreSQL" in destino.errores[0].mensaje


# --- Con el PostgreSQL de Docker ---

def _servidor() -> Conexion | None:
    con = Conexion.desde_entorno()
    try:
        con.conectar(con.bd_mantenimiento).close()
        return con
    except psycopg.Error:
        return None


SERVIDOR = _servidor()
postgres = pytest.mark.skipif(SERVIDOR is None, reason="PostgreSQL no está arrancado (docker compose up -d)")


def _sql(bd, *ordenes, autocommit=True):
    with SERVIDOR.conectar(bd, autocommit=autocommit) as c:
        for orden, *parametros in ordenes:
            c.execute(orden, *parametros)


@pytest.fixture
def con():
    """Servidor de la aplicación con un repositorio de pruebas propio (con la tabla del registro vacía)."""
    repositorio = f"test_repo_{uuid.uuid4().hex[:8]}"
    _sql(SERVIDOR.bd_mantenimiento, (f"CREATE DATABASE {repositorio}",))
    _sql(repositorio, (_TABLA_REGISTRO,))
    yield dataclasses.replace(SERVIDOR, bd_repositorio=repositorio)
    _sql(SERVIDOR.bd_mantenimiento, (f"DROP DATABASE IF EXISTS {repositorio} WITH (FORCE)",))


@pytest.fixture
def nombre():
    nombre = f"test_{uuid.uuid4().hex[:12]}"
    yield nombre
    _sql(SERVIDOR.bd_mantenimiento, (f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)",))


def registrar(con, nombre, servidor=""):
    _sql(con.bd_repositorio, ("""INSERT INTO bbdd_objetivo (servidor, nombre, ddl, filas, tablas, total_filas,
                                                            fichero_dump, bytes_dump)
                                 VALUES (%s, %s, 'CREATE TABLE a (id int);', '{"a": 1}', 1, 1, 'x.dump', 1)""",
                              (servidor, nombre)))


@postgres
def test_bbdd_registrada_y_existente(con, nombre):
    _sql(SERVIDOR.bd_mantenimiento, (f"CREATE DATABASE {nombre}",))
    registrar(con, nombre)
    r = analizar({"sql": "SELECT 1", "bbdd": nombre}, con).json()
    assert r["valido"] is True, r["errores"]
    assert r["bbdd"] == nombre and r["version"].startswith("17") and " " not in r["version"]


@postgres
def test_bbdd_que_no_esta_en_el_registro(con, nombre):
    # Existe en el servidor, pero no la ha generado el módulo 1.
    _sql(SERVIDOR.bd_mantenimiento, (f"CREATE DATABASE {nombre}",))
    r = analizar({"sql": "SELECT 1", "bbdd": nombre}, con).json()
    assert r["valido"] is False and "no es una BBDD objetivo" in r["errores"][0]["mensaje"]


@postgres
def test_solo_cuenta_el_registro_del_servidor_de_la_aplicacion(con, nombre):
    # Solo está registrada su copia en otro equipo (paso 9): la API no tiene su contraseña.
    _sql(SERVIDOR.bd_mantenimiento, (f"CREATE DATABASE {nombre}",))
    registrar(con, nombre, servidor="192.168.1.57:5432")
    r = analizar({"sql": "SELECT 1", "bbdd": nombre}, con).json()
    assert r["valido"] is False and "no es una BBDD objetivo" in r["errores"][0]["mensaje"]


@postgres
def test_bbdd_registrada_pero_borrada(con, nombre):
    registrar(con, nombre)
    r = analizar({"sql": "SELECT 1", "bbdd": nombre}, con).json()
    assert r["valido"] is False and "ya no existe en el servidor" in r["errores"][0]["mensaje"]


@postgres
def test_sin_repositorio_ninguna_es_bbdd_objetivo(nombre):
    # Todavía no se ha exportado ninguna BBDD: el repositorio no existe.
    _sql(SERVIDOR.bd_mantenimiento, (f"CREATE DATABASE {nombre}",))
    sin_repositorio = dataclasses.replace(SERVIDOR, bd_repositorio=f"test_repo_{uuid.uuid4().hex[:8]}")
    r = analizar({"sql": "SELECT 1", "bbdd": nombre}, sin_repositorio).json()
    assert r["valido"] is False and "no es una BBDD objetivo" in r["errores"][0]["mensaje"]
