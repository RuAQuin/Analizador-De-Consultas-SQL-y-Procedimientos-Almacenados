"""Paso 8: respaldo con COPY (SELECT 1) TO PROGRAM 'pg_dump ... -F c' y registro.

Los tests con PostgreSQL necesitan el contenedor de Docker (docker compose up -d); si no está arrancado,
se saltan. Crean BBDD «test_...», un repositorio propio «test_repo_...» (no tocan sqlanalyzer_repositorio)
y un directorio de dumps propio dentro del contenedor de PostgreSQL, y lo borran todo al terminar.
"""

import dataclasses
import subprocess
import time
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app, conexion, dumps, dumps_servidor
from sqlanalyzer_api.plano_datos import FICHERO_DUMP, Conexion
from sqlanalyzer_api.plano_datos import exportacion

cliente = TestClient(app)
SIN_SERVIDOR = Conexion(host="127.0.0.1", puerto=1)

TIENDA = """
CREATE TABLE compras (id serial PRIMARY KEY, cliente_id int NOT NULL REFERENCES clientes(id), importe numeric(8,2));
CREATE TABLE clientes (id serial PRIMARY KEY, nombre varchar(100) NOT NULL);
"""
FILAS = {"clientes": 3, "compras": 7}


def llamar(metodo, ruta, con, directorio, cuerpo=None, servidor="/tmp/no_usado"):
    app.dependency_overrides[conexion] = lambda: con
    app.dependency_overrides[dumps] = lambda: directorio
    app.dependency_overrides[dumps_servidor] = lambda: servidor
    try:
        return cliente.request(metodo, ruta, json=cuerpo)
    finally:
        app.dependency_overrides.clear()


def postgres_sh(orden, entrada=None):
    """Orden dentro del contenedor de PostgreSQL."""
    return subprocess.run(["docker", "exec", "-i", "sqlanalyzer-postgres", "sh", "-c", orden],
                          input=entrada, capture_output=True)


# --- Sin servidor ---

def test_nombres_de_dump_validos():
    for bueno in ["tienda_20261118_101500.dump", "tienda_20261118_101500.sql"]:
        assert FICHERO_DUMP.match(bueno)
    for malo in ["../etc/passwd", "tienda.dump", "Tienda_20261118_101500.dump", "tienda_20261118_101500.txt"]:
        assert not FICHERO_DUMP.match(malo)


def test_la_orden_de_pg_dump_va_entre_comillas_y_limpia_si_falla():
    ordenes = []

    class Conexion_:
        def execute(self, consulta):
            ordenes.append(consulta.as_string(None))

    exportacion._pg_dump(Conexion_(), "tienda", "/datos/dumps/tienda_20261118_101500.dump", Conexion())
    assert ordenes == ["COPY (SELECT 1) TO PROGRAM 'umask 022 && mkdir -p /datos/dumps && pg_dump -U postgres -d tienda -F c"
                       " -f /datos/dumps/tienda_20261118_101500.dump"
                       " || { rm -f /datos/dumps/tienda_20261118_101500.dump; exit 1; }'"]



def test_sin_servidor_avisa_de_la_conexion(tmp_path):
    r = llamar("POST", "/bbdd/exportar", SIN_SERVIDOR, tmp_path, {"nombre": "tienda", "ddl": TIENDA, "filas": FILAS}).json()
    assert r["valido"] is False
    assert "No se ha podido conectar con la base de datos «tienda»" in r["errores"][0]["mensaje"]


def test_nombre_reservado_no_conecta(tmp_path):
    r = llamar("POST", "/bbdd/exportar", SIN_SERVIDOR, tmp_path, {"nombre": "postgres", "ddl": TIENDA, "filas": FILAS}).json()
    assert "reservada" in r["errores"][0]["mensaje"]


def test_descarga_rechaza_rutas_y_ficheros_inexistentes(tmp_path):
    (tmp_path / "secreto.txt").write_text("x")
    assert llamar("GET", "/bbdd/dumps/secreto.txt", SIN_SERVIDOR, tmp_path).status_code == 404
    assert llamar("GET", "/bbdd/dumps/..%2Fsecreto.txt", SIN_SERVIDOR, tmp_path).status_code == 404
    assert llamar("GET", "/bbdd/dumps/tienda_20261118_101500.dump", SIN_SERVIDOR, tmp_path).status_code == 404


def test_descarga_un_dump(tmp_path):
    (tmp_path / "tienda_20261118_101500.dump").write_bytes(b"PGDMP\x01\x10")
    r = llamar("GET", "/bbdd/dumps/tienda_20261118_101500.dump", SIN_SERVIDOR, tmp_path)
    assert r.status_code == 200
    assert r.content == b"PGDMP\x01\x10"
    assert r.headers["content-type"] == "application/octet-stream"
    assert 'filename="tienda_20261118_101500.dump"' in r.headers["content-disposition"]


def test_descarga_un_script_de_exportaciones_anteriores(tmp_path):
    (tmp_path / "tienda_20261027_113817.sql").write_bytes(b"-- PostgreSQL database dump\n")
    r = llamar("GET", "/bbdd/dumps/tienda_20261027_113817.sql", SIN_SERVIDOR, tmp_path)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/sql")


def test_registro_sin_servidor_es_503(tmp_path):
    assert llamar("GET", "/bbdd/registro", SIN_SERVIDOR, tmp_path).status_code == 503


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


def _borrar(nombre):
    with SERVIDOR.conectar(SERVIDOR.bd_mantenimiento, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)")


@pytest.fixture
def con():
    """Conexión con un repositorio de pruebas propio."""
    repositorio = f"test_repo_{uuid.uuid4().hex[:8]}"
    yield dataclasses.replace(SERVIDOR, bd_repositorio=repositorio)
    _borrar(repositorio)


@pytest.fixture
def nombre():
    nombre = f"test_{uuid.uuid4().hex[:12]}"
    yield nombre
    _borrar(nombre)


@pytest.fixture
def servidor():
    """Directorio de dumps de pruebas dentro del contenedor de PostgreSQL."""
    directorio = f"/tmp/test_dumps_{uuid.uuid4().hex[:8]}"
    yield directorio
    postgres_sh(f"rm -rf {directorio}")



def ficheros(directorio):
    return postgres_sh(f"ls {directorio} 2>/dev/null").stdout.decode().split()


def cargar(nombre, con, tmp_path, analizar=True, ddl=TIENDA, filas=FILAS):
    cuerpo = {"nombre": nombre, "ddl": ddl, "filas": filas}
    for paso in ["crear", "insertar"] + (["analizar"] if analizar else []):
        r = llamar("POST", f"/bbdd/{paso}", con, tmp_path, cuerpo).json()
        assert r["valido"], r["errores"]
    return cuerpo


def exportar(con, tmp_path, cuerpo, servidor):
    return llamar("POST", "/bbdd/exportar", con, tmp_path, cuerpo, servidor).json()


@postgres
def test_respalda_en_formato_custom_y_lo_registra(nombre, con, tmp_path, servidor):
    cuerpo = cargar(nombre, con, tmp_path)
    r = exportar(con, tmp_path, cuerpo, servidor)
    assert r["valido"] is True, r["errores"]
    assert r["bbdd"] == nombre
    assert FICHERO_DUMP.match(r["fichero"]) and r["fichero"].startswith(nombre + "_")
    assert r["fichero"].endswith(".dump")
    assert ficheros(servidor) == [r["fichero"]]
    ruta = f"{servidor}/{r['fichero']}"
    # Formato custom: empieza por «PGDMP» y el tamaño es el del fichero en el servidor.
    assert postgres_sh(f"head -c 5 {ruta}").stdout == b"PGDMP"
    assert r["bytes"] == int(postgres_sh(f"stat -c %s {ruta}").stdout)
    # Legible para la API (otro usuario): -rw-r--r--.
    assert postgres_sh(f"stat -c %A {ruta}").stdout.decode().strip() == "-rw-r--r--"
    # pg_restore lo lee: tablas, datos y FK.
    contenido = postgres_sh(f"pg_restore --list {ruta}").stdout.decode()
    for entrada in ["TABLE public clientes", "TABLE public compras", "TABLE DATA public clientes",
                    "TABLE DATA public compras", "FK CONSTRAINT public compras compras_cliente_id_fkey"]:
        assert entrada in contenido

    registradas = llamar("GET", "/bbdd/registro", con, tmp_path).json()
    assert [(b["nombre"], b["tablas"], b["total_filas"], b["fichero"], b["existe"]) for b in registradas] == [
        (nombre, 2, 10, r["fichero"], True)]
    with con.conectar(con.bd_repositorio) as c:
        ddl, filas = c.execute("SELECT ddl, filas FROM bbdd_objetivo WHERE nombre = %s", (nombre,)).fetchone()
    assert ddl == TIENDA
    assert filas == {"clientes": 3, "compras": 7}


@postgres
def test_el_dump_se_puede_restaurar_con_pg_restore(nombre, con, tmp_path, servidor):
    cuerpo = cargar(nombre, con, tmp_path)
    r = exportar(con, tmp_path, cuerpo, servidor)
    _borrar(nombre)
    # --create: pg_restore crea la BBDD desde la BBDD de mantenimiento.
    restaurado = postgres_sh(f"pg_restore -U postgres -d postgres --create {servidor}/{r['fichero']}")
    assert restaurado.returncode == 0, restaurado.stderr.decode()
    with SERVIDOR.conectar(nombre) as c:
        assert c.execute("SELECT count(*) FROM clientes").fetchone()[0] == 3
        assert c.execute("SELECT count(*) FROM compras").fetchone()[0] == 7
        # Las secuencias siguen la numeración.
        assert c.execute("INSERT INTO clientes (nombre) VALUES ('Nuevo') RETURNING id").fetchone()[0] == 4
    assert llamar("GET", "/bbdd/registro", con, tmp_path).json()[0]["existe"] is True


@postgres
def test_sin_analyze_no_respalda(nombre, con, tmp_path, servidor):
    cuerpo = cargar(nombre, con, tmp_path, analizar=False)
    r = exportar(con, tmp_path, cuerpo, servidor)
    # Si el autovacuum se adelanta, la tabla ya estaría analizada: en ese caso sí se respalda.
    if not r["valido"]:
        assert r["errores"][0]["mensaje"] == (
            f"La tabla «clientes» de «{nombre}» no está analizada: ejecuta antes ANALYZE (paso 7)")
        assert ficheros(servidor) == []


@postgres
def test_si_pg_dump_falla_no_queda_nada(nombre, con, tmp_path, servidor, monkeypatch):
    cuerpo = cargar(nombre, con, tmp_path)
    # Un usuario que no existe: pg_dump termina con error.
    monkeypatch.setattr(exportacion, "_pg_dump", lambda c, n, ruta, conexion: exportacion._en_el_servidor(
        c, f"mkdir -p {servidor} && pg_dump -U nadie -d {n} -F c -f {ruta} || {{ rm -f {ruta}; exit 1; }}"))
    r = exportar(con, tmp_path, cuerpo, servidor)
    assert r["valido"] is False
    assert r["errores"][0]["mensaje"].startswith(f"pg_dump no ha podido respaldar «{nombre}»: ")
    assert ficheros(servidor) == []
    assert llamar("GET", "/bbdd/registro", con, tmp_path).json() == []


@postgres
def test_volver_a_respaldar_actualiza_el_registro(nombre, con, tmp_path, servidor):
    cuerpo = cargar(nombre, con, tmp_path)
    primero = exportar(con, tmp_path, cuerpo, servidor)
    time.sleep(1.1)  # Otro segundo: otro nombre de fichero.
    segundo = exportar(con, tmp_path, cuerpo, servidor)
    assert primero["fichero"] != segundo["fichero"]
    registradas = llamar("GET", "/bbdd/registro", con, tmp_path).json()
    assert [b["fichero"] for b in registradas] == [segundo["fichero"]]


@postgres
def test_registro_sin_repositorio_esta_vacio(con, tmp_path):
    assert llamar("GET", "/bbdd/registro", con, tmp_path).json() == []


@postgres
def test_bbdd_borrada_aparece_como_inexistente(nombre, con, tmp_path, servidor):
    cuerpo = cargar(nombre, con, tmp_path)
    exportar(con, tmp_path, cuerpo, servidor)
    _borrar(nombre)
    assert llamar("GET", "/bbdd/registro", con, tmp_path).json()[0]["existe"] is False


@postgres
def test_si_falla_el_registro_se_borra_el_dump(nombre, con, tmp_path, servidor, monkeypatch):
    cuerpo = cargar(nombre, con, tmp_path)

    def fallo(*_):
        raise psycopg.OperationalError("repositorio caído")

    monkeypatch.setattr(exportacion, "_registrar", fallo)
    r = exportar(con, tmp_path, cuerpo, servidor)
    assert r["valido"] is False
    assert "No se ha podido registrar" in r["errores"][0]["mensaje"]
    assert ficheros(servidor) == []
