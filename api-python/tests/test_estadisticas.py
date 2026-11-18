"""Paso 7: ANALYZE para cerrar la carga.

Los tests con PostgreSQL necesitan el contenedor de Docker (docker compose up -d); si no está arrancado,
se saltan. Crean BBDD «test_...» y las borran al terminar.
"""

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app, conexion
from sqlanalyzer_api.plano_datos import Conexion

cliente = TestClient(app)
SIN_SERVIDOR = Conexion(host="127.0.0.1", puerto=1)

TIENDA = """
CREATE TABLE lineas (id serial PRIMARY KEY, compra_id int NOT NULL REFERENCES compras(id), cantidad smallint);
CREATE TABLE compras (id serial PRIMARY KEY, cliente_id int NOT NULL REFERENCES clientes(id), importe numeric(8,2));
CREATE TABLE clientes (id serial PRIMARY KEY, nombre varchar(100) NOT NULL, activo boolean, alta date);
"""
FILAS = {"clientes": 3, "compras": 7, "lineas": 10}


def peticion(ruta, cuerpo, con):
    app.dependency_overrides[conexion] = lambda: con
    try:
        return cliente.post(ruta, json=cuerpo).json()
    finally:
        app.dependency_overrides.clear()


# --- Sin servidor ---

def test_sin_servidor_avisa_de_la_conexion():
    r = peticion("/bbdd/analizar", {"nombre": "tienda", "ddl": TIENDA, "filas": FILAS}, SIN_SERVIDOR)
    assert r["valido"] is False
    assert "No se ha podido conectar con la base de datos «tienda»" in r["errores"][0]["mensaje"]


def test_ddl_invalido_no_conecta():
    r = peticion("/bbdd/analizar", {"nombre": "tienda", "ddl": "CREATE TABLE (", "filas": {}}, SIN_SERVIDOR)
    assert r["valido"] is False
    assert r["errores"]


def test_nombre_reservado_no_conecta():
    r = peticion("/bbdd/analizar", {"nombre": "postgres", "ddl": TIENDA, "filas": FILAS}, SIN_SERVIDOR)
    assert "reservada" in r["errores"][0]["mensaje"]


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


@pytest.fixture
def nombre():
    nombre = f"test_{uuid.uuid4().hex[:12]}"
    yield nombre
    with SERVIDOR.conectar(SERVIDOR.bd_mantenimiento, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)")


def cuerpo(nombre, ddl=TIENDA, filas=FILAS):
    return {"nombre": nombre, "ddl": ddl, "filas": filas}


@postgres
def test_analyze_da_estadisticas_reales_en_orden_de_kahn(nombre):
    assert peticion("/bbdd/crear", cuerpo(nombre), SERVIDOR)["valido"]
    assert peticion("/bbdd/insertar", cuerpo(nombre), SERVIDOR)["valido"]
    r = peticion("/bbdd/analizar", cuerpo(nombre), SERVIDOR)
    assert r["valido"] is True, r["errores"]
    assert r["bbdd"] == nombre
    assert [t["tabla"] for t in r["tablas"]] == ["clientes", "compras", "lineas"]
    for t in r["tablas"]:
        assert t["estimadas"] == t["filas"] == FILAS[t["tabla"]]
        assert t["paginas"] >= 1
    # Una fila de pg_stats por columna.
    assert [t["columnas"] for t in r["tablas"]] == [4, 3, 3]


@postgres
def test_antes_del_analyze_postgresql_no_conoce_las_filas(nombre):
    assert peticion("/bbdd/crear", cuerpo(nombre), SERVIDOR)["valido"]
    assert peticion("/bbdd/insertar", cuerpo(nombre), SERVIDOR)["valido"]
    r = peticion("/bbdd/analizar", cuerpo(nombre), SERVIDOR)
    # -1: tabla nunca analizada (salvo que el autovacuum se haya adelantado).
    assert all(t["estimadas_antes"] in (-1, t["filas"]) for t in r["tablas"])


@postgres
def test_se_puede_repetir(nombre):
    assert peticion("/bbdd/crear", cuerpo(nombre), SERVIDOR)["valido"]
    assert peticion("/bbdd/insertar", cuerpo(nombre), SERVIDOR)["valido"]
    assert peticion("/bbdd/analizar", cuerpo(nombre), SERVIDOR)["valido"]
    r = peticion("/bbdd/analizar", cuerpo(nombre), SERVIDOR)
    assert r["valido"] is True
    assert [t["estimadas_antes"] for t in r["tablas"]] == [3, 7, 10]


@postgres
def test_sin_datos_insertados_no_analiza(nombre):
    assert peticion("/bbdd/crear", cuerpo(nombre), SERVIDOR)["valido"]
    r = peticion("/bbdd/analizar", cuerpo(nombre), SERVIDOR)
    assert r["valido"] is False
    assert r["errores"][0]["mensaje"] == (
        f"La tabla «clientes» de «{nombre}» está vacía: inserta antes los datos (paso 6)")


@postgres
def test_tabla_con_cero_filas_se_analiza(nombre):
    ddl = "CREATE TABLE a (id int PRIMARY KEY); CREATE TABLE b (id int PRIMARY KEY);"
    filas = {"a": 5, "b": 0}
    assert peticion("/bbdd/crear", cuerpo(nombre, ddl, filas), SERVIDOR)["valido"]
    assert peticion("/bbdd/insertar", cuerpo(nombre, ddl, filas), SERVIDOR)["valido"]
    r = peticion("/bbdd/analizar", cuerpo(nombre, ddl, filas), SERVIDOR)
    assert r["valido"] is True, r["errores"]
    assert [(t["tabla"], t["estimadas"]) for t in r["tablas"]] == [("a", 5), ("b", 0)]


@postgres
def test_bbdd_sin_crear(nombre):
    r = peticion("/bbdd/analizar", cuerpo(nombre), SERVIDOR)
    assert r["valido"] is False
    assert f"No se ha podido conectar con la base de datos «{nombre}»" in r["errores"][0]["mensaje"]


@postgres
def test_tablas_en_esquemas(nombre):
    ddl = """CREATE TABLE ventas.clientes (id int PRIMARY KEY);
             CREATE TABLE ventas.pedidos (id int PRIMARY KEY, cliente_id int REFERENCES ventas.clientes(id));"""
    filas = {"ventas.clientes": 2, "ventas.pedidos": 4}
    assert peticion("/bbdd/crear", cuerpo(nombre, ddl, filas), SERVIDOR)["valido"]
    assert peticion("/bbdd/insertar", cuerpo(nombre, ddl, filas), SERVIDOR)["valido"]
    r = peticion("/bbdd/analizar", cuerpo(nombre, ddl, filas), SERVIDOR)
    assert r["valido"] is True, r["errores"]
    assert [(t["tabla"], t["estimadas"], t["columnas"]) for t in r["tablas"]] == [
        ("ventas.clientes", 2, 1), ("ventas.pedidos", 4, 2)]
