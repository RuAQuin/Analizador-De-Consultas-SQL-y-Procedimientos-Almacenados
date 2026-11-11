"""Pasos 4 y 5: revisión del nombre, CREATE DATABASE y CREATE TABLE.

Los tests marcados con ``postgres`` necesitan el PostgreSQL de Docker (docker compose up -d);
si no está arrancado, se saltan.
"""

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app, conexion
from sqlanalyzer_api.plano_datos import Conexion, analizar_dependencias, crear_bbdd, parsear_ddl
from sqlanalyzer_api.plano_datos.creacion import esquemas_usados, revisar_nombre, sentencias_creacion

DDL = """
CREATE TABLE compras (id int PRIMARY KEY, cliente_id int NOT NULL REFERENCES clientes(id));
CREATE TABLE clientes (id serial PRIMARY KEY, nombre varchar(100) NOT NULL);
"""
FILAS = {"clientes": 3, "compras": 6}
# Puerto en el que no escucha nadie: si se intentara conectar, fallaría.
SIN_SERVIDOR = Conexion(host="127.0.0.1", puerto=1)

cliente = TestClient(app)


def analizar(ddl):
    resultado = parsear_ddl(ddl)
    return resultado.sentencias, analizar_dependencias(resultado.sentencias, ddl)


def crear(cuerpo, con=SIN_SERVIDOR):
    app.dependency_overrides[conexion] = lambda: con
    try:
        return cliente.post("/bbdd/crear", json=cuerpo).json()
    finally:
        app.dependency_overrides.clear()


# --- Sin servidor ---

def test_las_tablas_se_crean_en_el_orden_de_kahn():
    sentencias, dependencias = analizar(DDL)
    tablas = sentencias_creacion(sentencias, dependencias)
    assert [t.tabla for t in tablas] == ["clientes", "compras"]
    assert tablas[0].sentencia.startswith("CREATE TABLE clientes (id serial PRIMARY KEY")


def test_se_detectan_los_esquemas_del_ddl():
    sentencias, _ = analizar("CREATE TABLE ventas.a (id int); CREATE TABLE ventas.b (id int);"
                             " CREATE TABLE public.c (id int); CREATE TABLE d (id int);")
    assert esquemas_usados(sentencias) == ["ventas"]


@pytest.mark.parametrize("nombre", ["Tienda", "1tienda", "tienda-demo", "", "a" * 64])
def test_nombre_con_formato_invalido(nombre):
    assert "no es válido" in revisar_nombre(nombre, Conexion())[0].mensaje


@pytest.mark.parametrize("nombre", ["postgres", "template0", "template1", "sqlanalyzer_repositorio"])
def test_nombre_reservado(nombre):
    assert "reservada" in revisar_nombre(nombre, Conexion())[0].mensaje


def test_nombre_valido():
    assert revisar_nombre("tienda_demo", Conexion()) == []


def test_endpoint_ddl_invalido_no_conecta_con_postgres():
    r = crear({"nombre": "tienda", "ddl": "CREATE TABLE a (id int REFERENCES b(id));", "filas": {"a": 1}})
    assert r["valido"] is False
    assert "«b», que no está definida" in r["errores"][0]["mensaje"]
    assert r["tablas"] == []


def test_endpoint_prototipo_invalido_no_conecta_con_postgres():
    r = crear({"nombre": "tienda", "ddl": DDL, "filas": {"clientes": 0, "compras": 6}})
    assert r["valido"] is False
    assert "0 filas" in r["errores"][0]["mensaje"]


def test_endpoint_nombre_reservado_no_conecta_con_postgres():
    r = crear({"nombre": "postgres", "ddl": DDL, "filas": FILAS})
    assert r["valido"] is False
    assert "reservada" in r["errores"][0]["mensaje"]


def test_endpoint_sin_servidor_avisa_de_la_conexion():
    r = crear({"nombre": "tienda", "ddl": DDL, "filas": FILAS})
    assert r["valido"] is False
    assert "No se ha podido conectar con PostgreSQL (127.0.0.1:1)" in r["errores"][0]["mensaje"]


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
    """Nombre de una BBDD de prueba que se borra al terminar."""
    nombre = f"test_{uuid.uuid4().hex[:12]}"
    yield nombre
    with SERVIDOR.conectar(SERVIDOR.bd_mantenimiento, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)")


def _existe(nombre):
    with SERVIDOR.conectar(SERVIDOR.bd_mantenimiento) as c:
        return c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone() is not None


@postgres
def test_crea_la_bbdd_y_sus_tablas(nombre):
    r = crear({"nombre": nombre, "ddl": DDL, "filas": FILAS}, SERVIDOR)
    assert r["valido"] is True, r["errores"]
    assert r["bbdd"] == nombre
    assert [t["tabla"] for t in r["tablas"]] == ["clientes", "compras"]
    with SERVIDOR.conectar(nombre) as c:
        tablas = c.execute("SELECT table_name FROM information_schema.tables"
                           " WHERE table_schema = 'public' ORDER BY table_name").fetchall()
        fks = c.execute("SELECT count(*) FROM information_schema.table_constraints"
                        " WHERE constraint_type = 'FOREIGN KEY'").fetchone()[0]
    assert tablas == [("clientes",), ("compras",)]
    assert fks == 1


@postgres
def test_crea_los_esquemas(nombre):
    ddl = "CREATE TABLE ventas.clientes (id int PRIMARY KEY); CREATE TABLE ventas.compras (c int REFERENCES ventas.clientes(id));"
    r = crear({"nombre": nombre, "ddl": ddl, "filas": {"ventas.clientes": 1, "ventas.compras": 1}}, SERVIDOR)
    assert r["valido"] is True, r["errores"]
    assert r["esquemas"] == ["ventas"]
    with SERVIDOR.conectar(nombre) as c:
        assert c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'ventas'").fetchone()[0] == 2


@postgres
def test_bbdd_que_ya_existe(nombre):
    assert crear({"nombre": nombre, "ddl": DDL, "filas": FILAS}, SERVIDOR)["valido"] is True
    r = crear({"nombre": nombre, "ddl": DDL, "filas": FILAS}, SERVIDOR)
    assert r["valido"] is False
    assert f"Ya existe una base de datos «{nombre}»" in r["errores"][0]["mensaje"]


@postgres
def test_si_falla_un_create_table_no_queda_la_bbdd(nombre):
    # pglast lo parsea, pero PostgreSQL no: la columna del CHECK no existe.
    ddl = "CREATE TABLE a (id int PRIMARY KEY); CREATE TABLE b (id int CHECK (no_existe > 0));"
    sentencias, dependencias = analizar(ddl)
    creacion = crear_bbdd(nombre, sentencias, dependencias, SERVIDOR)
    assert not creacion.valido
    assert "«b»" in creacion.errores[0].mensaje
    assert "no_existe" in creacion.errores[0].mensaje
    assert not _existe(nombre)
