"""Paso 6.3: escribir las tuplas en PostgreSQL, tabla a tabla en el orden de Kahn.

Los tests que escriben en PostgreSQL necesitan el contenedor de Docker (docker compose up -d);
si no está arrancado, se saltan. Crean BBDD «test_...» y las borran al terminar.
"""

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app, conexion
from sqlanalyzer_api.plano_datos import (Conexion, Tupla, agrupar_por_tabla, analizar_dependencias, formar_arboles,
                                         generar_carga, ordenar_arboles, parsear_ddl, preparar_generador)
from sqlanalyzer_api.plano_datos.insercion import AUTO

cliente = TestClient(app)
SIN_SERVIDOR = Conexion(host="127.0.0.1", puerto=1)


def peticion(ruta, cuerpo, con):
    app.dependency_overrides[conexion] = lambda: con
    try:
        return cliente.post(ruta, json=cuerpo).json()
    finally:
        app.dependency_overrides.clear()


# --- Sin servidor ---

def test_agrupa_por_tabla_en_orden_de_kahn_y_quita_las_columnas_auto():
    tuplas = [Tupla("clientes", 0, ("id", "alta"), (1, AUTO)),
              Tupla("compras", 0, ("id", "cliente_id"), (1, 1)),
              Tupla("clientes", 1, ("id", "alta"), (2, AUTO)),
              Tupla("compras", 1, ("id", "cliente_id"), (2, 2))]
    lotes = agrupar_por_tabla(tuplas, ["clientes", "compras", "vacia"])
    assert [(l.tabla, l.columnas, l.filas) for l in lotes] == [
        ("clientes", ("id",), [(1,), (2,)]),
        ("compras", ("id", "cliente_id"), [(1, 1), (2, 2)]),
        ("vacia", (), [])]


def test_las_tuplas_del_diagrama_quedan_ordenadas_por_id_en_cada_tabla():
    ddl = """CREATE TABLE clientes (id serial PRIMARY KEY);
             CREATE TABLE compras (id serial PRIMARY KEY, cliente_id int REFERENCES clientes(id));"""
    resultado = parsear_ddl(ddl)
    dependencias = analizar_dependencias(resultado.sentencias, ddl)
    arboles = formar_arboles(dependencias)
    filas = {"clientes": 3, "compras": 7}
    generador = preparar_generador(resultado.sentencias, dependencias, filas).generador
    lotes = agrupar_por_tabla(generar_carga(arboles, ordenar_arboles(dependencias, arboles, ddl), generador),
                              ["clientes", "compras"])
    assert [f[0] for f in lotes[1].filas] == [1, 2, 3, 4, 5, 6, 7]
    assert [f[1] for f in lotes[1].filas] == [1, 1, 1, 2, 2, 3, 3]


def test_endpoint_sin_servidor_avisa_de_la_conexion():
    r = peticion("/bbdd/insertar", {"nombre": "tienda", "ddl": "CREATE TABLE a (id int PRIMARY KEY);",
                                    "filas": {"a": 2}}, SIN_SERVIDOR)
    assert r["valido"] is False
    assert "No se ha podido conectar con la base de datos «tienda»" in r["errores"][0]["mensaje"]


def test_endpoint_prototipo_invalido_no_conecta():
    r = peticion("/bbdd/insertar", {"nombre": "tienda", "ddl": "CREATE TABLE t (b boolean UNIQUE);",
                                    "filas": {"t": 3}}, SIN_SERVIDOR)
    assert r["valido"] is False
    assert "repetiría valores" in r["errores"][0]["mensaje"]


def test_endpoint_nombre_reservado_no_conecta():
    r = peticion("/bbdd/insertar", {"nombre": "postgres", "ddl": "CREATE TABLE a (id int);", "filas": {"a": 1}},
                 SIN_SERVIDOR)
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


def crear_e_insertar(nombre, ddl, filas):
    cuerpo = {"nombre": nombre, "ddl": ddl, "filas": filas}
    creada = peticion("/bbdd/crear", cuerpo, SERVIDOR)
    assert creada["valido"], creada["errores"]
    return peticion("/bbdd/insertar", cuerpo, SERVIDOR)


def consulta(nombre, sql):
    with SERVIDOR.conectar(nombre) as c:
        return c.execute(sql).fetchall()


TIENDA = """
CREATE TABLE lineas (id serial PRIMARY KEY, compra_id int NOT NULL REFERENCES compras(id), cantidad smallint);
CREATE TABLE compras (id serial PRIMARY KEY, cliente_id int NOT NULL REFERENCES clientes(id), importe numeric(8,2));
CREATE TABLE clientes (id serial PRIMARY KEY, nombre varchar(100) NOT NULL, activo boolean, alta date);
"""


@postgres
def test_inserta_todas_las_filas_en_orden_de_kahn(nombre):
    r = crear_e_insertar(nombre, TIENDA, {"clientes": 3, "compras": 7, "lineas": 10})
    assert r["valido"] is True, r["errores"]
    assert r["tablas"] == [{"tabla": "clientes", "filas": 3}, {"tabla": "compras", "filas": 7},
                           {"tabla": "lineas", "filas": 10}]
    assert consulta(nombre, "SELECT count(*) FROM clientes")[0][0] == 3
    assert consulta(nombre, "SELECT id, nombre, activo FROM clientes ORDER BY id") == [
        (1, "AAA", True), (2, "BBB", False), (3, "CCC", True)]
    # Reparto en bloques: 3, 2 y 2 compras por cliente.
    assert consulta(nombre, "SELECT cliente_id, count(*) FROM compras GROUP BY 1 ORDER BY 1") == [(1, 3), (2, 2), (3, 2)]


@postgres
def test_fk_dentro_del_mismo_arbol(nombre):
    # envios cuelga de compras y además apunta a direcciones: en el preorden del árbol va antes,
    # pero se escribe tabla a tabla en orden de Kahn y la FK se cumple.
    ddl = """
    CREATE TABLE clientes (id int PRIMARY KEY);
    CREATE TABLE compras (id int PRIMARY KEY, cliente_id int NOT NULL REFERENCES clientes(id));
    CREATE TABLE direcciones (id int PRIMARY KEY, cliente_id int NOT NULL REFERENCES clientes(id));
    CREATE TABLE envios (id int PRIMARY KEY, compra_id int NOT NULL REFERENCES compras(id),
                         direccion_id int NOT NULL REFERENCES direcciones(id));
    """
    r = crear_e_insertar(nombre, ddl, {"clientes": 2, "compras": 4, "direcciones": 4, "envios": 8})
    assert r["valido"] is True, r["errores"]
    assert consulta(nombre, "SELECT count(*) FROM envios")[0][0] == 8


@postgres
def test_secuencias_ajustadas_y_columnas_que_rellena_postgresql(nombre):
    ddl = """CREATE TABLE t (id serial PRIMARY KEY, n int GENERATED ALWAYS AS IDENTITY,
                             alta timestamp DEFAULT now(), doble int GENERATED ALWAYS AS (id * 2) STORED);"""
    r = crear_e_insertar(nombre, ddl, {"t": 3})
    assert r["valido"] is True, r["errores"]
    with SERVIDOR.conectar(nombre) as c:
        assert c.execute("SELECT id, n, doble, alta IS NOT NULL FROM t ORDER BY id").fetchall() == [
            (1, 1, 2, True), (2, 2, 4, True), (3, 3, 6, True)]
        # El siguiente INSERT del usuario sigue la numeración.
        assert c.execute("INSERT INTO t DEFAULT VALUES RETURNING id, n").fetchone() == (4, 4)


@postgres
def test_tabla_sin_columnas_que_escribir(nombre):
    r = crear_e_insertar(nombre, "CREATE TABLE eventos (alta timestamp DEFAULT now());", {"eventos": 4})
    assert r["valido"] is True, r["errores"]
    assert consulta(nombre, "SELECT count(*) FROM eventos")[0][0] == 4


@postgres
def test_esquemas(nombre):
    ddl = "CREATE TABLE ventas.c (id int PRIMARY KEY); CREATE TABLE ventas.d (c int REFERENCES ventas.c(id));"
    r = crear_e_insertar(nombre, ddl, {"ventas.c": 2, "ventas.d": 3})
    assert r["valido"] is True, r["errores"]
    assert consulta(nombre, "SELECT count(*) FROM ventas.d")[0][0] == 3


@postgres
def test_si_falla_una_fila_no_se_inserta_nada(nombre):
    # El CHECK no lo tiene en cuenta el prototipo: la fila 2 (cantidad = 2) lo incumple.
    ddl = """CREATE TABLE productos (id int PRIMARY KEY);
             CREATE TABLE lineas (id int PRIMARY KEY, cantidad int CHECK (cantidad <> 2));"""
    r = crear_e_insertar(nombre, ddl, {"productos": 3, "lineas": 3})
    assert r["valido"] is False
    assert "la fila 2 de «lineas»" in r["errores"][0]["mensaje"]
    assert "No se ha insertado ningún dato" in r["errores"][0]["mensaje"]
    # productos se había escrito antes, pero la transacción se ha deshecho.
    assert consulta(nombre, "SELECT count(*) FROM productos")[0][0] == 0


@postgres
def test_no_se_inserta_dos_veces(nombre):
    ddl = "CREATE TABLE a (id int PRIMARY KEY);"
    assert crear_e_insertar(nombre, ddl, {"a": 2})["valido"] is True
    r = peticion("/bbdd/insertar", {"nombre": nombre, "ddl": ddl, "filas": {"a": 2}}, SERVIDOR)
    assert r["valido"] is False
    assert "ya tiene filas" in r["errores"][0]["mensaje"]
    assert consulta(nombre, "SELECT count(*) FROM a")[0][0] == 2


@postgres
def test_bbdd_que_no_existe():
    r = peticion("/bbdd/insertar", {"nombre": f"no_existe_{uuid.uuid4().hex[:8]}", "ddl": "CREATE TABLE a (id int);",
                                    "filas": {"a": 1}}, SERVIDOR)
    assert r["valido"] is False
    assert "No se ha podido conectar con la base de datos" in r["errores"][0]["mensaje"]
