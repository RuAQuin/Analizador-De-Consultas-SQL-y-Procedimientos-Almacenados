"""Paso 6: progreso de la inserción (reloj de la carga en la WebApp).

Los tests que escriben en PostgreSQL necesitan el contenedor de Docker (docker compose up -d);
si no está arrancado, se saltan. Crean BBDD «test_...» y las borran al terminar.
"""

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app, conexion
from sqlanalyzer_api.plano_datos import Conexion, ProgresoCarga, Tupla, progreso_insercion
from sqlanalyzer_api.plano_datos import insercion
from sqlanalyzer_api.plano_datos.insercion import AVISO_CADA, ESCRIBIENDO, GENERANDO

cliente = TestClient(app)
SIN_SERVIDOR = Conexion(host="127.0.0.1", puerto=1)

TIENDA = """
CREATE TABLE lineas (id serial PRIMARY KEY, compra_id int NOT NULL REFERENCES compras(id), cantidad smallint);
CREATE TABLE compras (id serial PRIMARY KEY, cliente_id int NOT NULL REFERENCES clientes(id), importe numeric(8,2));
CREATE TABLE clientes (id serial PRIMARY KEY, nombre varchar(100) NOT NULL, activo boolean, alta date);
"""


def peticion(ruta, cuerpo, con):
    app.dependency_overrides[conexion] = lambda: con
    try:
        return cliente.post(ruta, json=cuerpo).json()
    finally:
        app.dependency_overrides.clear()


def consultar_progreso(nombre):
    return cliente.get(f"/bbdd/insertar/progreso/{nombre}")


# --- Sin servidor ---

def test_sin_insercion_en_marcha_da_404():
    r = consultar_progreso("tienda_sin_carga")
    assert r.status_code == 404
    assert "No hay ninguna inserción en marcha en «tienda_sin_carga»" in r.json()["detail"]


def test_cuenta_las_tuplas_generadas_cada_aviso_y_al_terminar():
    progreso = ProgresoCarga(GENERANDO, total=AVISO_CADA + 5)
    tuplas = (Tupla("t", i, ("id",), (i,)) for i in range(AVISO_CADA + 5))
    vistos = []
    for i, _ in enumerate(insercion._contando(tuplas, progreso), start=1):
        if i in (AVISO_CADA, AVISO_CADA + 1):
            vistos.append(progreso.hechas)
    assert vistos == [AVISO_CADA, AVISO_CADA] # Se actualiza cada AVISO_CADA filas, no en cada una.
    assert progreso.hechas == AVISO_CADA + 5 # Y al terminar, con el total exacto.


def test_el_progreso_se_quita_aunque_la_insercion_falle():
    nombre = "tienda_sin_servidor"
    r = peticion("/bbdd/insertar", {"nombre": nombre, "ddl": "CREATE TABLE a (id int PRIMARY KEY);",
                                    "filas": {"a": 2}}, SIN_SERVIDOR)
    assert r["valido"] is False
    assert progreso_insercion(nombre) is None
    assert consultar_progreso(nombre).status_code == 404


def test_la_consulta_devuelve_una_copia():
    nombre = "tienda_copia"
    insercion._EN_MARCHA[nombre] = ProgresoCarga(ESCRIBIENDO, total=10, hechas=4, tabla="clientes")
    try:
        copia = progreso_insercion(nombre)
        copia.hechas = 99
        assert consultar_progreso(nombre).json() == {"fase": "escribiendo", "tabla": "clientes",
                                                     "hechas": 4, "total": 10}
    finally:
        del insercion._EN_MARCHA[nombre]


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


@postgres
def test_el_progreso_avanza_tabla_a_tabla_y_se_quita_al_terminar(nombre, monkeypatch):
    # Tras escribir cada tabla se consulta el endpoint, como hace la WebApp mientras dura la inserción.
    vistos = []
    escribir = insercion._escribir

    def escribir_y_consultar(c, lote, progreso=None):
        escribir(c, lote, progreso)
        vistos.append(consultar_progreso(nombre).json())

    monkeypatch.setattr(insercion, "_escribir", escribir_y_consultar)
    cuerpo = {"nombre": nombre, "ddl": TIENDA, "filas": {"clientes": 3, "compras": 7, "lineas": 10}}
    assert peticion("/bbdd/crear", cuerpo, SERVIDOR)["valido"]
    r = peticion("/bbdd/insertar", cuerpo, SERVIDOR)

    assert r["valido"] is True, r["errores"]
    # Las filas escritas se acumulan en el orden de Kahn hasta el total (3 + 7 + 10).
    assert vistos == [{"fase": "escribiendo", "tabla": "clientes", "hechas": 3, "total": 20},
                      {"fase": "escribiendo", "tabla": "compras", "hechas": 10, "total": 20},
                      {"fase": "escribiendo", "tabla": "lineas", "hechas": 20, "total": 20}]
    assert consultar_progreso(nombre).status_code == 404
