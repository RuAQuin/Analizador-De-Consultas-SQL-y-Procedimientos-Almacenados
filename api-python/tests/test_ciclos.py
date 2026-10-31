"""Resolución automática de ciclos de FK con tablas intermedias."""

from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app
from sqlanalyzer_api.plano_datos import analizar_dependencias, parsear_ddl, resolver_ciclos

E2 = """CREATE TABLE departamentos (
  id integer PRIMARY KEY,
  nombre varchar(100) NOT NULL,
  responsable_id integer REFERENCES empleados(id)
);

CREATE TABLE empleados (
  id integer PRIMARY KEY,
  departamento_id integer REFERENCES departamentos(id)
);

CREATE TABLE nominas (
  id integer PRIMARY KEY,
  empleado_id integer REFERENCES empleados(id)
);"""


def resolver_y_ordenar(ddl: str):
    """Resuelve los ciclos y comprueba que el DDL resultante parsea y se ordena sin errores."""
    resolucion = resolver_ciclos(ddl)
    assert not resolucion.errores, resolucion.errores
    resultado = parsear_ddl(resolucion.ddl)
    assert resultado.valido, resultado.errores
    dependencias = analizar_dependencias(resultado.sentencias, resolucion.ddl)
    assert dependencias.valido, dependencias.errores
    return resolucion, dependencias


def test_sin_ciclos_el_ddl_no_cambia():
    ddl = "CREATE TABLE a (id int PRIMARY KEY);\nCREATE TABLE b (a_id int REFERENCES a);"
    resolucion = resolver_ciclos(ddl)
    assert resolucion.ddl == ddl and resolucion.intermedias == []


def test_e2_crea_tabla_intermedia():
    resolucion, dep = resolver_y_ordenar(E2)
    [intermedia] = resolucion.intermedias
    assert intermedia.tabla == "departamentos_responsable"
    assert (intermedia.sustituye.tabla, intermedia.sustituye.columnas) == ("departamentos", ("responsable_id",))
    assert "departamentos_id integer PRIMARY KEY REFERENCES departamentos (id)" in intermedia.ddl
    assert "responsable_id integer NOT NULL REFERENCES empleados (id)" in intermedia.ddl
    # responsable_id desaparece de departamentos; el resto de columnas se conserva.
    departamentos = resolucion.ddl.split(";")[0]
    assert "responsable_id" not in departamentos and "nombre varchar(100) NOT NULL" in departamentos
    assert [(o.tabla, o.nivel) for o in dep.orden] == [
        ("departamentos", 0), ("empleados", 1), ("nominas", 2), ("departamentos_responsable", 2)]


def test_tablas_sin_cambios_conservan_el_texto_del_usuario():
    resolucion, _ = resolver_y_ordenar(E2)
    assert "CREATE TABLE empleados (\n  id integer PRIMARY KEY,\n  departamento_id integer REFERENCES departamentos(id)\n)" \
        in resolucion.ddl


def test_se_aparta_la_fk_que_apunta_mas_abajo_en_el_ddl():
    # Igual que E2 pero con las tablas al revés: ahora se aparta empleados.departamento_id.
    ddl = """CREATE TABLE empleados (id int PRIMARY KEY, departamento_id int REFERENCES departamentos(id));
             CREATE TABLE departamentos (id int PRIMARY KEY, responsable_id int REFERENCES empleados(id));"""
    resolucion, _ = resolver_y_ordenar(ddl)
    assert resolucion.intermedias[0].tabla == "empleados_departamento"


def test_ciclo_de_tres_tablas():
    ddl = """CREATE TABLE a (id int PRIMARY KEY, c_id int REFERENCES c);
             CREATE TABLE b (id int PRIMARY KEY, a_id int REFERENCES a);
             CREATE TABLE c (id int PRIMARY KEY, b_id int REFERENCES b);"""
    resolucion, dep = resolver_y_ordenar(ddl)
    assert [i.tabla for i in resolucion.intermedias] == ["a_c"]
    assert [o.tabla for o in dep.orden][:3] == ["a", "b", "c"]


def test_dos_ciclos_independientes():
    ddl = """CREATE TABLE a (id int PRIMARY KEY, b_id int REFERENCES b);
             CREATE TABLE b (id int PRIMARY KEY, a_id int REFERENCES a);
             CREATE TABLE x (id int PRIMARY KEY, y_id int REFERENCES y);
             CREATE TABLE y (id int PRIMARY KEY, x_id int REFERENCES x);"""
    resolucion, _ = resolver_y_ordenar(ddl)
    assert [i.tabla for i in resolucion.intermedias] == ["a_b", "x_y"]


def test_pk_compuesta_y_fk_de_tabla():
    ddl = """CREATE TABLE pedidos (
               serie char(1), numero int, cliente_zona int, cliente_num int,
               PRIMARY KEY (serie, numero),
               FOREIGN KEY (cliente_zona, cliente_num) REFERENCES clientes (zona, num)
             );
             CREATE TABLE clientes (
               zona int, num int, ultimo_serie char(1), ultimo_numero int,
               PRIMARY KEY (zona, num),
               FOREIGN KEY (ultimo_serie, ultimo_numero) REFERENCES pedidos (serie, numero)
             );"""
    resolucion, _ = resolver_y_ordenar(ddl)
    [intermedia] = resolucion.intermedias
    assert intermedia.tabla == "pedidos_clientes"
    assert "PRIMARY KEY (pedidos_serie, pedidos_numero)" in intermedia.ddl
    assert "FOREIGN KEY (pedidos_serie, pedidos_numero) REFERENCES pedidos (serie, numero)" in intermedia.ddl
    assert "FOREIGN KEY (cliente_zona, cliente_num) REFERENCES clientes (zona, num)" in intermedia.ddl
    assert "cliente_zona" not in resolucion.ddl.split(";")[0]


def test_serial_y_unique_se_trasladan():
    ddl = """CREATE TABLE a (id serial PRIMARY KEY, b_id int UNIQUE REFERENCES b);
             CREATE TABLE b (id bigserial PRIMARY KEY, a_id int REFERENCES a);"""
    resolucion, _ = resolver_y_ordenar(ddl)
    sql = resolucion.intermedias[0].ddl
    assert "a_id integer PRIMARY KEY" in sql  # serial -> integer
    assert "b_id integer NOT NULL UNIQUE REFERENCES b" in sql


def test_si_una_fk_no_se_puede_apartar_se_usa_otra():
    # La FK de a tiene un CHECK: se aparta la de b aunque esté más arriba la de a.
    ddl = """CREATE TABLE a (id int PRIMARY KEY, b_id int REFERENCES b CHECK (b_id > 0));
             CREATE TABLE b (id int PRIMARY KEY, a_id int REFERENCES a);"""
    resolucion, _ = resolver_y_ordenar(ddl)
    assert resolucion.intermedias[0].tabla == "b_a"


def test_nombre_de_tabla_intermedia_ocupado():
    ddl = """CREATE TABLE a (id int PRIMARY KEY, b_id int REFERENCES b);
             CREATE TABLE b (id int PRIMARY KEY, a_id int REFERENCES a);
             CREATE TABLE a_b (id int);"""
    resolucion, _ = resolver_y_ordenar(ddl)
    assert resolucion.intermedias[0].tabla == "a_b_2"


def test_ciclo_sin_pk_no_se_puede_resolver():
    ddl = """CREATE TABLE a (b_id int REFERENCES b);
             CREATE TABLE b (a_id int REFERENCES a);"""
    resolucion = resolver_ciclos(ddl)
    [error] = resolucion.errores
    assert "«a», «b»" in error.mensaje and "no tiene PK" in error.mensaje


def test_autorreferencia_no_se_toca():
    ddl = "CREATE TABLE empleados (id int PRIMARY KEY, jefe_id int REFERENCES empleados);"
    assert resolver_ciclos(ddl).intermedias == []


cliente = TestClient(app)


def test_endpoint_e2_es_valido_con_tabla_intermedia():
    cuerpo = cliente.post("/bbdd/ddl", json={"ddl": E2}).json()
    assert cuerpo["valido"] is True
    assert cuerpo["tablas_intermedias"] == [{"tabla": "departamentos_responsable", "sustituye": {
        "tabla": "departamentos", "columnas": ["responsable_id"], "tabla_padre": "empleados", "columnas_padre": ["id"]}}]
    assert "CREATE TABLE departamentos_responsable" in cuerpo["ddl_final"]
    assert "departamentos_responsable" in cuerpo["tablas"]


def test_endpoint_sin_ciclos_devuelve_el_ddl_original():
    ddl = "CREATE TABLE a (id int PRIMARY KEY);"
    cuerpo = cliente.post("/bbdd/ddl", json={"ddl": ddl}).json()
    assert cuerpo["ddl_final"] == ddl and cuerpo["tablas_intermedias"] == []


def test_endpoint_ciclo_irresoluble_no_es_valido():
    cuerpo = cliente.post("/bbdd/ddl", json={"ddl": "CREATE TABLE a (b_id int REFERENCES b);\n"
                                                    "CREATE TABLE b (a_id int REFERENCES a);"}).json()
    assert cuerpo["valido"] is False and cuerpo["ddl_final"] is None
    assert "no se puede romper automáticamente" in cuerpo["errores"][0]["mensaje"]
