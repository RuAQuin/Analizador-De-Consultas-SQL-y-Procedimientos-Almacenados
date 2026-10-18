"""Test de integración: genera una BBDD real. Se salta si no hay PG_CONTRASENA en el entorno."""

import os
import shutil

import psycopg
import pytest

from sqlanalyzer_api.config import ConfigPostgres
from sqlanalyzer_api.plano_datos import EspecificacionBbdd, generar_bbdd
from sqlanalyzer_api.plano_datos.ejecucion import BbddYaExiste, eliminar_bbdd

pytestmark = pytest.mark.skipif("PG_CONTRASENA" not in os.environ,
                                reason="define PG_HOST, PG_USUARIO y PG_CONTRASENA para ejecutarlo")

NOMBRE = "sqlanalyzer_test_generacion"

ESPEC = {
    "nombre": NOMBRE,
    "semilla": 0.5,
    "tablas": [
        {"nombre": "compras", "tuplas": 20000, "columnas": [
            {"nombre": "id", "tipo": "bigint", "identidad": True, "pk": True},
            {"nombre": "cliente_id", "tipo": "integer", "fk": {"tabla": "clientes"}},
            {"nombre": "fecha", "tipo": "timestamp"},
            {"nombre": "estado", "tipo": "varchar(20)", "distribucion": [
                {"valor": "ENTREGADO", "porcentaje": 90}, {"valor": "CANCELADO", "porcentaje": 10}]},
        ]},
        {"nombre": "clientes", "tuplas": 500, "columnas": [
            {"nombre": "id", "tipo": "integer", "identidad": True, "pk": True},
            {"nombre": "email", "tipo": "varchar(60)", "unico": True},
            {"nombre": "telefono", "tipo": "varchar(15)", "nulable": True, "porcentaje_nulos": 50},
        ]},
        {"nombre": "paises", "tuplas": 0, "columnas": [
            {"nombre": "codigo", "tipo": "char(2)", "pk": True},
            {"nombre": "nombre", "tipo": "text"},
        ], "inserts": "INSERT INTO paises VALUES ('ES', 'España'), ('PT', 'Portugal');"},
    ],
}


@pytest.fixture
def config(tmp_path):
    base = ConfigPostgres.desde_entorno()
    config = ConfigPostgres(**{**base.__dict__, "bd_repositorio": NOMBRE + "_repo", "directorio_dumps": tmp_path})
    yield config
    eliminar_bbdd(config, NOMBRE)
    eliminar_bbdd(config, config.bd_repositorio)


def test_genera_carga_analiza_y_registra(config):
    tiene_pg_dump = shutil.which(config.pg_dump) is not None
    resultado = generar_bbdd(EspecificacionBbdd.model_validate(ESPEC), config,
                             reemplazar=True, exportar=tiene_pg_dump)

    assert resultado.orden == ["clientes", "paises", "compras"]
    assert {t.nombre: t.tuplas for t in resultado.tablas} == {"clientes": 500, "paises": 2, "compras": 20000}

    with psycopg.connect(**config.conexion(NOMBRE)) as conn:
        entregados = conn.execute("SELECT avg((estado = 'ENTREGADO')::int) FROM compras").fetchone()[0]
        assert 0.87 < entregados < 0.93
        nulos = conn.execute("SELECT avg((telefono IS NULL)::int) FROM clientes").fetchone()[0]
        assert 0.4 < nulos < 0.6
        fks = conn.execute("SELECT conname FROM pg_constraint WHERE contype = 'f'").fetchall()
        assert fks == [("fk_compras_cliente_id",)]
        # ANALYZE ejecutado: hay estadísticas de las tablas.
        assert conn.execute("SELECT count(*) FROM pg_stats WHERE tablename = 'compras'").fetchone()[0] > 0

    if tiene_pg_dump:
        assert "CREATE TABLE public.compras" in resultado.ruta_dump.read_text(encoding="utf-8")

    with psycopg.connect(**config.conexion(config.bd_repositorio)) as conn:
        fila = conn.execute("SELECT origen, tablas FROM bbdd WHERE id = %s", (resultado.id_registro,)).fetchone()
    assert fila[0] == "GENERADA" and len(fila[1]) == 3

    with pytest.raises(BbddYaExiste):
        generar_bbdd(EspecificacionBbdd.model_validate(ESPEC), config, exportar=False, registrar=False)
