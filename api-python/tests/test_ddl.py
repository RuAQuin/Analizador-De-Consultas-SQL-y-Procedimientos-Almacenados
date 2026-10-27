"""Paso 1 del módulo 1: parseo con pglast del DDL escrito por el usuario."""

from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app
from sqlanalyzer_api.plano_datos import parsear_ddl

DDL_VALIDO = """
CREATE TABLE clientes (
    id integer PRIMARY KEY,
    email varchar(60) UNIQUE
);
CREATE TABLE compras (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cliente_id integer NOT NULL REFERENCES clientes(id)
);
"""


def test_ddl_valido_devuelve_las_tablas():
    resultado = parsear_ddl(DDL_VALIDO)
    assert resultado.valido
    assert resultado.tablas == ["clientes", "compras"]
    assert len(resultado.sentencias) == 2


def test_error_de_sintaxis_indica_linea_y_columna():
    ddl = "CREATE TABLE a (\n  id integer PRIMARY KEY,\n  nombre text NOT NUL\n);"
    resultado = parsear_ddl(ddl)
    assert not resultado.valido
    [error] = resultado.errores
    assert error.mensaje.startswith("Error de sintaxis")
    assert "NUL" in error.mensaje
    assert (error.linea, error.columna) == (3, 19)


def test_ddl_vacio():
    resultado = parsear_ddl("   \n ")
    assert not resultado.valido
    assert "vacío" in resultado.errores[0].mensaje


def test_solo_comentarios():
    resultado = parsear_ddl("-- nada que crear")
    assert not resultado.valido


def test_rechaza_sentencias_que_no_son_create_table():
    ddl = "CREATE TABLE a (id int);\nINSERT INTO a VALUES (1);"
    resultado = parsear_ddl(ddl)
    assert not resultado.valido
    [error] = resultado.errores
    assert "CREATE TABLE" in error.mensaje and "InsertStmt" in error.mensaje
    assert error.linea == 2


def test_tabla_con_esquema():
    assert parsear_ddl("CREATE TABLE ventas.pedidos (id int);").tablas == ["ventas.pedidos"]


cliente = TestClient(app)


def test_endpoint_ddl_valido():
    r = cliente.post("/bbdd/ddl", json={"ddl": DDL_VALIDO})
    assert r.status_code == 200
    assert r.json() == {"valido": True, "tablas": ["clientes", "compras"], "errores": []}


def test_endpoint_ddl_con_error():
    r = cliente.post("/bbdd/ddl", json={"ddl": "CREATE TABLA a (id int);"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["valido"] is False
    assert cuerpo["errores"][0]["linea"] == 1


def test_salud():
    assert cliente.get("/salud").json() == {"estado": "ok"}
