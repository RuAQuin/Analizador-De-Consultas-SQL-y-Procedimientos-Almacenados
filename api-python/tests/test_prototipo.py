"""Paso 3 del módulo 1: el usuario define el prototipo de datos (número de filas por tabla)."""

from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app
from sqlanalyzer_api.plano_datos import analizar_dependencias, generar_prototipo, parsear_ddl

TIENDA = """
CREATE TABLE clientes (id serial PRIMARY KEY, nombre varchar(100) NOT NULL, email varchar(10) UNIQUE,
                       activo boolean, alta date);
CREATE TABLE productos (codigo char(4) PRIMARY KEY, precio numeric(6,2), peso real, creado timestamp DEFAULT now());
CREATE TABLE compras (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                      cliente_id int NOT NULL REFERENCES clientes, hora time, ref uuid);
CREATE TABLE lineas (compra_id bigint REFERENCES compras(id), num int,
                     producto char(4) REFERENCES productos, PRIMARY KEY (compra_id, num));
"""
FILAS = {"clientes": 3, "productos": 2, "compras": 6, "lineas": 8}


def prototipo(ddl: str, filas: dict):
    resultado = parsear_ddl(ddl)
    assert resultado.valido, resultado.errores
    dep = analizar_dependencias(resultado.sentencias, ddl)
    assert dep.valido, dep.errores
    return generar_prototipo(resultado.sentencias, dep, filas)


def tabla(proto, nombre):
    return next(t for t in proto.tablas if t.tabla == nombre)


def columna(proto, nombre_tabla, nombre_columna) -> list[str]:
    t = tabla(proto, nombre_tabla)
    i = [c.nombre for c in t.columnas].index(nombre_columna)
    return [fila[i] for fila in t.muestra]


def test_valores_segun_el_tipo():
    proto = prototipo(TIENDA, FILAS)
    assert proto.valido, proto.errores
    assert columna(proto, "clientes", "nombre") == ["AAA", "BBB", "CCC"]
    assert columna(proto, "clientes", "activo") == ["true", "false", "true"]
    assert columna(proto, "clientes", "alta") == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert columna(proto, "productos", "precio") == ["1.00", "2.00"]
    assert columna(proto, "productos", "peso") == ["1.0", "2.0"]
    assert columna(proto, "compras", "hora")[:2] == ["00:00:00", "00:00:01"]
    assert columna(proto, "compras", "ref")[0] == "00000000-0000-4000-8000-000000000001"
    assert columna(proto, "lineas", "num") == ["1", "2", "3", "4", "5"]


def test_columnas_que_rellena_postgresql():
    proto = prototipo(TIENDA, FILAS)
    assert columna(proto, "clientes", "id") == ["(auto)"] * 3          # serial
    assert columna(proto, "compras", "id") == ["(auto)"] * 5           # IDENTITY
    assert columna(proto, "productos", "creado") == ["(auto)"] * 2     # DEFAULT
    assert tabla(proto, "compras").origenes == ["auto", "fk", "tipo", "tipo"]


def test_fk_toma_valores_del_padre_por_turnos():
    proto = prototipo(TIENDA, FILAS)
    # 6 compras repartidas entre 3 clientes (ids 1, 2, 3 de su serial).
    assert columna(proto, "compras", "cliente_id") == ["1", "2", "3", "1", "2"]
    # La FK a una PK de texto toma el valor de texto del padre.
    assert set(columna(proto, "lineas", "producto")) <= {"AAA", "BBB"}


def test_muestra_de_como_maximo_5_filas_y_orden_de_kahn():
    proto = prototipo(TIENDA, FILAS)
    assert [t.tabla for t in proto.tablas] == ["clientes", "productos", "compras", "lineas"]
    assert [len(t.muestra) for t in proto.tablas] == [3, 2, 5, 5]
    assert [t.filas for t in proto.tablas] == [3, 2, 6, 8]


def test_texto_sin_repetir_mas_alla_de_la_z():
    proto = prototipo("CREATE TABLE t (c text PRIMARY KEY);", {"t": 1000})
    assert proto.valido


def test_texto_recortado_a_su_longitud():
    proto = prototipo("CREATE TABLE t (c char(2));", {"t": 2})
    assert columna(proto, "t", "c") == ["AA", "BB"]


def test_autorreferencia_nulable_queda_a_null():
    proto = prototipo("CREATE TABLE e (id int PRIMARY KEY, jefe_id int REFERENCES e);", {"e": 2})
    assert columna(proto, "e", "jefe_id") == ["NULL", "NULL"]


def test_pk_compuesta_de_fk_no_repite_combinaciones():
    ddl = """CREATE TABLE alumnos (id int PRIMARY KEY);
             CREATE TABLE asignaturas (id int PRIMARY KEY);
             CREATE TABLE matriculas (asignatura_id int REFERENCES asignaturas, alumno_id int REFERENCES alumnos,
                                      PRIMARY KEY (asignatura_id, alumno_id));"""
    proto = prototipo(ddl, {"alumnos": 3, "asignaturas": 2, "matriculas": 6})
    assert proto.valido
    t = tabla(proto, "matriculas")
    assert len({tuple(f) for f in t.muestra}) == len(t.muestra)
    # 2 × 3 = 6 combinaciones: la séptima fila repetiría la PK.
    [error] = prototipo(ddl, {"alumnos": 3, "asignaturas": 2, "matriculas": 7}).errores
    assert "(asignatura_id, alumno_id)" in error.mensaje
    assert "a partir de la fila 7" in error.mensaje


# --- Avisos de coherencia ---

def test_falta_el_numero_de_filas():
    [error] = prototipo(TIENDA, {"clientes": 3, "productos": 2, "compras": 6}).errores
    assert error.mensaje == "Indica el número de filas de «lineas»"


def test_numero_de_filas_fuera_de_rango():
    errores = prototipo(TIENDA, {**FILAS, "clientes": -1, "lineas": 100_001}).errores
    assert len(errores) == 2
    assert all("debe estar entre 0 y 100.000" in e.mensaje for e in errores)


def test_tabla_que_no_esta_en_el_ddl():
    [error] = prototipo(TIENDA, {**FILAS, "otra": 5}).errores
    assert error.mensaje == "La tabla «otra» no está en el DDL"


def test_fk_not_null_a_tabla_sin_filas():
    [error] = prototipo(TIENDA, {**FILAS, "clientes": 0}).errores
    assert "«compras» tiene 6 filas" in error.mensaje
    assert "apunta a «clientes», que tiene 0 filas" in error.mensaje


def test_fk_nulable_a_tabla_sin_filas_queda_a_null():
    proto = prototipo(TIENDA, {**FILAS, "productos": 0})
    assert proto.valido
    assert set(columna(proto, "lineas", "producto")) == {"NULL"}


def test_tipo_que_no_se_puede_generar():
    errores = prototipo("CREATE TABLE t (a json, b int[], c interval);", {"t": 1}).errores
    assert [e.mensaje for e in errores] == [
        "La columna «t.a» es de tipo json, que no se puede generar",
        "La columna «t.b» es de tipo integer[], que no se puede generar",
        "La columna «t.c» es de tipo interval, que no se puede generar"]


def test_clave_unica_que_se_quedaria_sin_valores():
    # boolean solo tiene dos valores distintos.
    [error] = prototipo("CREATE TABLE t (b boolean UNIQUE);", {"t": 3}).errores
    assert "La clave única (b) de «t» repetiría valores a partir de la fila 3" in error.mensaje


cliente = TestClient(app)


def test_endpoint_prototipo():
    cuerpo = cliente.post("/bbdd/prototipo", json={"ddl": TIENDA, "filas": FILAS}).json()
    assert cuerpo["valido"] is True
    clientes = cuerpo["tablas"][0]
    assert clientes["tabla"] == "clientes"
    assert clientes["filas"] == 3
    assert clientes["columnas"][1] == {"nombre": "nombre", "tipo": "varchar(100)", "origen": "tipo"}
    assert clientes["muestra"][0] == ["(auto)", "AAA", "AAA", "true", "2024-01-01"]


def test_endpoint_prototipo_con_aviso():
    cuerpo = cliente.post("/bbdd/prototipo", json={"ddl": TIENDA, "filas": {**FILAS, "clientes": 0}}).json()
    assert cuerpo["valido"] is False
    assert cuerpo["tablas"] == []
    assert "dale filas a «clientes»" in cuerpo["errores"][0]["mensaje"]


def test_endpoint_prototipo_con_ddl_invalido_devuelve_sus_errores():
    cuerpo = cliente.post("/bbdd/prototipo", json={"ddl": "CREATE TABLA a (id int);", "filas": {}}).json()
    assert cuerpo["valido"] is False
    assert cuerpo["errores"][0]["mensaje"].startswith("Error de sintaxis")
