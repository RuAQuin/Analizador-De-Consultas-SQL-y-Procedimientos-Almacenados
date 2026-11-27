"""Paso 9: restaurar la BBDD (el respaldo del paso 8) en el PostgreSQL de otro equipo de la red.

En los tests con PostgreSQL, el de Docker hace también de «servidor de otro equipo»: se genera la BBDD, se
exporta (paso 8), se borra y se restaura en el mismo servidor indicándolo como servidor de destino. Como
pg_restore puede no estar instalado en este equipo, se sustituye por el del contenedor (mismo resultado).
Si PostgreSQL no está arrancado (docker compose up -d), esos tests se saltan. Crean BBDD «test_...», un
repositorio propio «test_repo_...» y un directorio de dumps propio, y lo borran todo al terminar.
"""

import dataclasses
import shutil
import subprocess
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from sqlanalyzer_api.app import ServidorDto, _destino, app, conexion, dumps, dumps_servidor
from sqlanalyzer_api.plano_datos import Conexion, restauracion
from sqlanalyzer_api.plano_datos.creacion import pista_conexion

cliente = TestClient(app)
# subprocess.run original (los tests lo sustituyen con monkeypatch, que lo cambia en todo el proceso).
EJECUTAR = subprocess.run
APLICACION = Conexion(host="postgres", puerto=5432, bd_repositorio="sqlanalyzer_repositorio")
OTRO = {"host": "192.168.1.57", "puerto": 5432, "usuario": "ana", "contrasena": "secreta"}

TIENDA = """
CREATE TABLE compras (id serial PRIMARY KEY, cliente_id int NOT NULL REFERENCES clientes(id), importe numeric(8,2));
CREATE TABLE clientes (id serial PRIMARY KEY, nombre varchar(100) NOT NULL);
"""
FILAS = {"clientes": 3, "compras": 7}


def llamar(metodo, ruta, con, cuerpo=None, directorio=None, servidor="/tmp/no_usado"):
    app.dependency_overrides[conexion] = lambda: con
    app.dependency_overrides[dumps] = lambda: directorio
    app.dependency_overrides[dumps_servidor] = lambda: servidor
    try:
        return cliente.request(metodo, ruta, json=cuerpo)
    finally:
        app.dependency_overrides.clear()


# --- Sin servidor ---

def test_el_servidor_indicado_sustituye_host_puerto_y_usuario():
    destino = _destino(ServidorDto(**OTRO), APLICACION)
    assert (destino.host, destino.puerto, destino.usuario, destino.contrasena) == ("192.168.1.57", 5432, "ana", "secreta")
    assert destino.bd_mantenimiento == "postgres"
    # El repositorio de la aplicación sigue siendo un nombre reservado también en el otro servidor.
    assert destino.bd_repositorio == "sqlanalyzer_repositorio"


def test_localhost_es_el_equipo_de_la_api_si_corre_en_docker(monkeypatch):
    servidor = ServidorDto(host="localhost", puerto=5434, usuario="ana")
    monkeypatch.delenv("HOST_LOCAL", raising=False)
    assert _destino(servidor, APLICACION).host == "localhost"
    monkeypatch.setenv("HOST_LOCAL", "host.docker.internal")
    assert _destino(servidor, APLICACION).host == "host.docker.internal"
    assert _destino(ServidorDto(**OTRO), APLICACION).host == "192.168.1.57"


def test_la_contrasena_no_aparece_al_mostrar_la_conexion():
    texto = repr(Conexion(host="192.168.1.57", usuario="ana", contrasena="secreta"))
    assert "secreta" not in texto and "ana@192.168.1.57" in texto


def test_pistas_de_los_errores_de_conexion():
    assert "contraseña" in pista_conexion(psycopg.OperationalError('password authentication failed for user "ana"'))
    assert "pg_hba.conf" in pista_conexion(psycopg.OperationalError('no pg_hba.conf entry for host "10.0.0.2"'))
    assert "listen_addresses" in pista_conexion(psycopg.OperationalError("Connection refused"))
    assert pista_conexion(psycopg.OperationalError("otra cosa")) == ""


def test_probar_un_servidor_que_no_responde():
    r = llamar("POST", "/bbdd/servidor/probar", APLICACION, {**OTRO, "host": "127.0.0.1", "puerto": 1}).json()
    assert r["valido"] is False and r["servidor"] == "127.0.0.1:1"
    assert "No se ha podido conectar con PostgreSQL (127.0.0.1:1)" in r["errores"][0]["mensaje"]
    assert "Posible causa: el servidor no responde" in r["errores"][0]["mensaje"]


def test_el_servidor_se_valida():
    r = llamar("POST", "/bbdd/restaurar", APLICACION, {"nombre": "tienda", "fichero": "tienda_20261124_101500.dump",
                                                       "servidor": {"host": "", "puerto": 70000, "usuario": "ana"}})
    assert r.status_code == 422


def test_solo_se_restauran_respaldos_del_paso_8(tmp_path):
    for fichero in ["../secreto.dump", "tienda_20261027_113817.sql"]:
        r = llamar("POST", "/bbdd/restaurar", APLICACION, {"nombre": "tienda", "fichero": fichero, "servidor": OTRO},
                   tmp_path).json()
        assert r["valido"] is False and "no es un respaldo del paso 8" in r["errores"][0]["mensaje"]
    r = llamar("POST", "/bbdd/restaurar", APLICACION, {"nombre": "tienda", "fichero": "tienda_20261124_101500.dump",
                                                       "servidor": OTRO}, tmp_path).json()
    assert "No existe el respaldo «tienda_20261124_101500.dump»" in r["errores"][0]["mensaje"]


def test_pg_restore_pasa_la_contrasena_por_el_entorno(tmp_path, monkeypatch):
    llamadas = []

    def ejecutar(orden, env, **_):
        llamadas.append((orden, env))
        return subprocess.CompletedProcess(orden, 0, "", "")

    monkeypatch.setattr(restauracion.subprocess, "run", ejecutar)
    dump = tmp_path / "tienda_20261124_101500.dump"
    restauracion._pg_restore(dump, Conexion(host="192.168.1.57", puerto=5432, usuario="ana", contrasena="secreta"))
    [(orden, entorno)] = llamadas
    assert orden == ["pg_restore", "-h", "192.168.1.57", "-p", "5432", "-U", "ana", "-d", "postgres", "--create",
                     "--no-owner", "--no-privileges", "--exit-on-error", str(dump)]
    assert "secreta" not in " ".join(orden) # No se ve en la lista de procesos.
    assert entorno["PGPASSWORD"] == "secreta"


def test_si_pg_restore_falla_se_explica(tmp_path, monkeypatch):
    def ejecutar(orden, **_):
        return subprocess.CompletedProcess(orden, 1, "", "pg_restore: error: could not execute query: ERROR:  syntax"
                                                         " error\npg_restore: warning: errors ignored on restore: 1\n")

    monkeypatch.setattr(restauracion.subprocess, "run", ejecutar)
    with pytest.raises(restauracion._FalloRestauracion, match="^could not execute query: ERROR:  syntax error$"):
        restauracion._pg_restore(tmp_path / "tienda_20261124_101500.dump", Conexion())


def test_sin_pg_restore_instalado_se_explica(tmp_path, monkeypatch):
    def ejecutar(orden, **_):
        raise FileNotFoundError(orden[0])

    monkeypatch.setattr(restauracion.subprocess, "run", ejecutar)
    with pytest.raises(restauracion._FalloRestauracion, match="pg_restore no está instalado en la API"):
        restauracion._pg_restore(tmp_path / "tienda_20261124_101500.dump", Conexion())


# --- Con el PostgreSQL de Docker haciendo también de «servidor de otro equipo» ---

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


def _existe(nombre):
    with SERVIDOR.conectar(SERVIDOR.bd_mantenimiento) as c:
        return c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone() is not None


def postgres_sh(orden, entrada=None):
    """Orden dentro del contenedor de PostgreSQL."""
    return EJECUTAR(["docker", "exec", "-i", "sqlanalyzer-postgres", "sh", "-c", orden], input=entrada, capture_output=True)


@pytest.fixture
def aplicacion():
    """Servidor de la aplicación con un repositorio de pruebas propio."""
    repositorio = f"test_repo_{uuid.uuid4().hex[:8]}"
    yield dataclasses.replace(SERVIDOR, bd_repositorio=repositorio)
    _borrar(repositorio)


@pytest.fixture
def nombre():
    nombre = f"test_{uuid.uuid4().hex[:12]}"
    yield nombre
    _borrar(nombre)


def otro() -> dict:
    """El PostgreSQL de Docker, indicado como servidor de otro equipo."""
    return {"host": SERVIDOR.host, "puerto": SERVIDOR.puerto, "usuario": SERVIDOR.usuario,
            "contrasena": SERVIDOR.contrasena}


def pg_restore_desde_docker(orden, env, **_):
    """Sustituye a pg_restore si no está instalado en este equipo: le pasa el dump al del contenedor."""
    with open(orden[-1], "rb") as f:
        r = EJECUTAR(["docker", "exec", "-i", "sqlanalyzer-postgres", "pg_restore", "-U", orden[orden.index("-U") + 1],
                      *orden[orden.index("-d"):-1]], input=f.read(), capture_output=True)
    return subprocess.CompletedProcess(orden, r.returncode, "", r.stderr.decode())


def exportada(nombre, aplicacion, tmp_path):
    """Pasos 5 a 8 en el servidor de la aplicación; devuelve el dump copiado en tmp_path (el directorio de la API)."""
    directorio = f"/tmp/test_dumps_{uuid.uuid4().hex[:8]}"
    cuerpo = {"nombre": nombre, "ddl": TIENDA, "filas": FILAS}
    try:
        for paso in ["crear", "insertar", "analizar", "exportar"]:
            r = llamar("POST", f"/bbdd/{paso}", aplicacion, cuerpo, tmp_path, directorio).json()
            assert r["valido"], (paso, r["errores"])
        dump = tmp_path / r["fichero"]
        dump.write_bytes(postgres_sh(f"cat {directorio}/{r['fichero']}").stdout)
    finally:
        postgres_sh(f"rm -rf {directorio}")
    return dump


@pytest.fixture
def con_pg_restore(monkeypatch):
    if shutil.which("pg_restore") is None:
        monkeypatch.setattr(restauracion.subprocess, "run", pg_restore_desde_docker)


@postgres
def test_probar_el_servidor(aplicacion):
    r = llamar("POST", "/bbdd/servidor/probar", aplicacion, otro()).json()
    assert r["valido"] is True, r["errores"]
    assert r["servidor"] == f"{SERVIDOR.host}:{SERVIDOR.puerto}"
    assert r["version"].startswith("17")


@postgres
def test_probar_con_un_usuario_que_no_puede_crear_bbdd(aplicacion):
    rol = f"test_rol_{uuid.uuid4().hex[:8]}"
    with SERVIDOR.conectar(SERVIDOR.bd_mantenimiento, autocommit=True) as c:
        c.execute(f"CREATE ROLE {rol} LOGIN PASSWORD 'clave'")
    try:
        r = llamar("POST", "/bbdd/servidor/probar", aplicacion, {**otro(), "usuario": rol, "contrasena": "clave"}).json()
        assert r["valido"] is False
        assert f"ALTER ROLE {rol} CREATEDB" in r["errores"][0]["mensaje"]
        # Con una contraseña incorrecta, la pista lo dice.
        r = llamar("POST", "/bbdd/servidor/probar", aplicacion, {**otro(), "usuario": rol, "contrasena": "otra"}).json()
        assert "el usuario o la contraseña no son correctos" in r["errores"][0]["mensaje"]
    finally:
        with SERVIDOR.conectar(SERVIDOR.bd_mantenimiento, autocommit=True) as c:
            c.execute(f"DROP ROLE IF EXISTS {rol}")


@postgres
def test_restaura_analiza_y_registra_en_el_otro_servidor(nombre, aplicacion, tmp_path, con_pg_restore):
    dump = exportada(nombre, aplicacion, tmp_path)
    _borrar(nombre) # En el «otro servidor» (el mismo) no puede existir: --create la crea.

    r = llamar("POST", "/bbdd/restaurar", aplicacion, {"nombre": nombre, "fichero": dump.name, "servidor": otro()},
               tmp_path).json()
    assert r["valido"] is True, r["errores"]
    assert r["servidor"] == f"{SERVIDOR.host}:{SERVIDOR.puerto}" and r["version"].startswith("17")
    # Datos restaurados y analizados (reltuples exacto tras el ANALYZE).
    assert r["tablas"] == [{"tabla": "clientes", "filas": 3}, {"tabla": "compras", "filas": 7}]
    with SERVIDOR.conectar(nombre) as c:
        assert c.execute("SELECT count(*) FROM compras").fetchone()[0] == 7
    # Registrada como BBDD objetivo de ese servidor, además de la del paso 8.
    registradas = llamar("GET", "/bbdd/registro", aplicacion).json()
    assert sorted((x["servidor"], x["nombre"], x["total_filas"], x["existe"]) for x in registradas) == [
        ("", nombre, 10, True), (f"{SERVIDOR.host}:{SERVIDOR.puerto}", nombre, 10, None)]


@postgres
def test_no_se_restaura_si_ya_existe_en_el_otro_servidor(nombre, aplicacion, tmp_path):
    dump = exportada(nombre, aplicacion, tmp_path)
    r = llamar("POST", "/bbdd/restaurar", aplicacion, {"nombre": nombre, "fichero": dump.name, "servidor": otro()},
               tmp_path).json()
    assert f"Ya existe una base de datos «{nombre}» en {SERVIDOR.host}:{SERVIDOR.puerto}" in r["errores"][0]["mensaje"]


@postgres
def test_si_pg_restore_falla_no_queda_nada(nombre, aplicacion, tmp_path, monkeypatch):
    dump = exportada(nombre, aplicacion, tmp_path)
    _borrar(nombre)

    def a_medias(orden, **_):
        # Crea la BBDD (como haría --create) y falla después.
        with SERVIDOR.conectar(SERVIDOR.bd_mantenimiento, autocommit=True) as c:
            c.execute(f"CREATE DATABASE {nombre}")
        return subprocess.CompletedProcess(orden, 1, "", "pg_restore: error: could not execute query: ERROR:  boom\n")

    monkeypatch.setattr(restauracion.subprocess, "run", a_medias)
    r = llamar("POST", "/bbdd/restaurar", aplicacion, {"nombre": nombre, "fichero": dump.name, "servidor": otro()},
               tmp_path).json()
    assert "pg_restore no ha podido restaurar" in r["errores"][0]["mensaje"] and "boom" in r["errores"][0]["mensaje"]
    assert not _existe(nombre)


@postgres
def test_solo_el_respaldo_registrado_de_esa_bbdd(nombre, aplicacion, tmp_path):
    dump = exportada(nombre, aplicacion, tmp_path)
    otro_dump = tmp_path / f"{nombre}_20200101_000000.dump"
    otro_dump.write_bytes(dump.read_bytes())
    r = llamar("POST", "/bbdd/restaurar", aplicacion, {"nombre": nombre, "fichero": otro_dump.name, "servidor": otro()},
               tmp_path).json()
    assert "no es el respaldo registrado" in r["errores"][0]["mensaje"]

