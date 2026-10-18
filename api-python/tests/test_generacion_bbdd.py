"""Tests del generador de BBDD que no necesitan PostgreSQL (pasos 1, 2, 3 y 5)."""

import json
from pathlib import Path

import pytest
from pglast import parse_sql
from pydantic import ValidationError

from sqlanalyzer_api.plano_datos import ErrorValidacion, EspecificacionBbdd, validar
from sqlanalyzer_api.plano_datos.datos import expresion_valor
from sqlanalyzer_api.plano_datos.ordenacion import CicloDeClavesForaneas, ordenar_tablas
from sqlanalyzer_api.plano_datos.sql import analizar_tipo, ident, literal

EJEMPLO = Path(__file__).parents[1] / "ejemplos" / "compras.json"


def espec(*tablas, nombre="prueba"):
    return EspecificacionBbdd.model_validate({"nombre": nombre, "tablas": list(tablas)})


def tabla(nombre, *columnas, tuplas=10, **extra):
    return {"nombre": nombre, "tuplas": tuplas, "columnas": list(columnas), **extra}


PK = {"nombre": "id", "tipo": "integer", "identidad": True, "pk": True}


def errores(e: EspecificacionBbdd) -> str:
    with pytest.raises(ErrorValidacion) as info:
        validar(e)
    return "\n".join(info.value.errores)


# ----------------------------------------------------------------- especificación

def test_nombres_invalidos_se_rechazan():
    with pytest.raises(ValidationError):
        espec(tabla("Clientes; DROP", PK))
    with pytest.raises(ValidationError):
        espec(tabla("a", PK), nombre="Mi BBDD")


def test_distribucion_que_supera_el_100_por_cien():
    with pytest.raises(ValidationError, match="suma 110"):
        espec(tabla("a", PK, {"nombre": "e", "tipo": "text", "distribucion": [
            {"valor": "X", "porcentaje": 60}, {"valor": "Y", "porcentaje": 50}]}))


def test_pk_nulable_y_nulos_sin_nulable():
    with pytest.raises(ValidationError, match="PK no puede ser nulable"):
        espec(tabla("a", {**PK, "nulable": True}))
    with pytest.raises(ValidationError, match="porcentaje_nulos exige"):
        espec(tabla("a", PK, {"nombre": "x", "tipo": "text", "porcentaje_nulos": 10}))


# ------------------------------------------------------------------------- tipos

@pytest.mark.parametrize("texto, familia", [
    ("int", "entero"), ("BIGINT", "entero"), ("numeric(12,2)", "decimal"), ("double precision", "flotante"),
    ("bool", "booleano"), ("date", "fecha"), ("timestamptz", "marca_tiempo"), ("varchar(20)", "texto"),
    ("char(3)", "texto"), ("uuid", "uuid"),
])
def test_tipos_admitidos(texto, familia):
    assert analizar_tipo(texto).familia == familia


@pytest.mark.parametrize("texto", ["serial", "int[]", "json", "int); DROP TABLE x; --", "int NOT NULL", "nada de nada"])
def test_tipos_rechazados(texto):
    with pytest.raises(ValueError):
        analizar_tipo(texto)


def test_literales_e_identificadores():
    assert literal("O'Brien") == "'O''Brien'"
    assert literal(None) == "NULL" and literal(True) == "TRUE"
    assert ident("user") == '"user"' and ident("clientes") == "clientes"


# --------------------------------------------------------------- validación (FK)

def test_fk_a_tabla_inexistente():
    assert "no existe en la especificación" in errores(
        espec(tabla("b", PK, {"nombre": "a_id", "tipo": "integer", "fk": {"tabla": "a"}})))


def test_fk_a_la_propia_tabla():
    assert "debe apuntar a otra tabla" in errores(
        espec(tabla("b", PK, {"nombre": "padre", "tipo": "integer", "fk": {"tabla": "b"}})))


def test_fk_a_columna_que_no_es_pk_ni_unq():
    e = espec(tabla("a", PK, {"nombre": "codigo", "tipo": "integer"}),
              tabla("b", PK, {"nombre": "a_cod", "tipo": "integer", "fk": {"tabla": "a", "columna": "codigo"}}))
    assert "no es PK ni UNQ" in errores(e)


def test_fk_de_tipo_incompatible():
    e = espec(tabla("a", PK), tabla("b", PK, {"nombre": "a_id", "tipo": "text", "fk": {"tabla": "a"}}))
    assert "no es compatible" in errores(e)


def test_fk_obligatoria_sin_tuplas_en_el_padre():
    e = espec(tabla("a", PK, tuplas=0), tabla("b", PK, {"nombre": "a_id", "tipo": "integer", "fk": {"tabla": "a"}}))
    assert "no tiene tuplas que referenciar" in errores(e)


def test_errores_se_acumulan():
    e = espec(tabla("a", PK, {"nombre": "x", "tipo": "jsonb"}),
              tabla("b", PK, {"nombre": "z_id", "tipo": "integer", "fk": {"tabla": "z"}}))
    texto = errores(e)
    assert "jsonb" in texto and "'z' no existe" in texto


def test_inserts_recibidos_deben_ser_de_su_tabla():
    e = espec(tabla("a", PK, {"nombre": "n", "tipo": "text"}, inserts="INSERT INTO otra (n) VALUES ('x');"))
    assert "dirigido a otra tabla" in errores(e)
    e = espec(tabla("a", PK, {"nombre": "n", "tipo": "text"}, inserts="DELETE FROM a;"))
    assert "solo se admiten sentencias INSERT" in errores(e)


# ------------------------------------------------------------------- ordenación

def test_orden_padres_antes_que_hijas():
    e = espec(
        tabla("lineas", PK, {"nombre": "pedido_id", "tipo": "integer", "fk": {"tabla": "pedidos"}}),
        tabla("pedidos", PK, {"nombre": "cliente_id", "tipo": "integer", "fk": {"tabla": "clientes"}}),
        tabla("clientes", PK),
    )
    assert ordenar_tablas(e) == ["clientes", "pedidos", "lineas"]


def test_ciclo_de_fk():
    e = espec(tabla("a", PK, {"nombre": "b_id", "tipo": "integer", "fk": {"tabla": "b"}}),
              tabla("b", PK, {"nombre": "a_id", "tipo": "integer", "fk": {"tabla": "a"}}))
    with pytest.raises(CicloDeClavesForaneas):
        ordenar_tablas(e)
    assert "ciclo" in errores(e)


# ----------------------------------------------------------------- generación SQL

def test_ejemplo_del_esquema_funcional():
    validado = validar(EspecificacionBbdd.model_validate(json.loads(EJEMPLO.read_text(encoding="utf-8"))))
    assert validado.orden == ["a", "c", "b"]
    assert "GENERATED ALWAYS AS IDENTITY PRIMARY KEY" in validado.tablas["b"]
    assert "FOREIGN KEY" not in validado.tablas["b"]
    carga_b = validado.cargas["b"]
    assert "generate_series(1, 2000000)" in carga_b
    assert "WHEN s.r1 < 0.85 THEN CAST('ENTREGADO' AS varchar(20))" in carga_b
    assert "ELSE CAST('CANCELADO' AS varchar(20))" in carga_b
    assert validado.claves_foraneas == [
        "ALTER TABLE b ADD CONSTRAINT fk_b_cliente_id FOREIGN KEY (cliente_id) REFERENCES a (id);",
        "ALTER TABLE b ADD CONSTRAINT fk_b_producto_id FOREIGN KEY (producto_id) REFERENCES c (id);",
    ]
    # Todo el script (DDL + carga + FK) lo acepta pglast, con las FK al final.
    script = validado.script
    assert len(parse_sql(script)) == 3 + 3 + 2
    assert script.index("INSERT INTO b") < script.index("ALTER TABLE b")


def test_distribucion_parcial_completa_con_aleatorios():
    e = espec(tabla("a", PK, {"nombre": "ciudad", "tipo": "varchar(30)",
                              "distribucion": [{"valor": "Burgos", "porcentaje": 90}]}))
    carga = validar(e).cargas["a"]
    assert "WHEN s.r1 < 0.9 THEN CAST('Burgos' AS varchar(30)) ELSE substr(md5" in carga


def test_columnas_unicas_se_generan_desde_el_indice():
    e = espec(tabla("a", {"nombre": "codigo", "tipo": "integer", "pk": True, "minimo": 100},
                    {"nombre": "email", "tipo": "varchar(40)", "unico": True}))
    carga = validar(e).cargas["a"]
    assert "(s.i::bigint + 99)::integer" in carga
    assert "('email_' || s.i)" in carga


def test_unicidad_imposible():
    col = EspecificacionBbdd.model_validate({"nombre": "x", "tablas": [tabla(
        "a", {"nombre": "n", "tipo": "smallint", "pk": True})]}).tablas[0].columnas[0]
    with pytest.raises(ValueError, match="no caben"):
        expresion_valor(col, analizar_tipo("smallint"), 40000)
    e = espec(tabla("a", PK, {"nombre": "cod", "tipo": "char(2)", "unico": True}, tuplas=500))
    assert "demasiado corto" in errores(e)


def test_valor_de_distribucion_de_otro_tipo():
    e = espec(tabla("a", PK, {"nombre": "n", "tipo": "integer", "distribucion": [{"valor": "uno", "porcentaje": 50}]}))
    assert "no es de tipo integer" in errores(e)


def test_inserts_recibidos_sustituyen_a_la_generacion():
    inserts = "INSERT INTO a (n) VALUES ('x'), ('y');"
    e = espec(tabla("a", PK, {"nombre": "n", "tipo": "text"}, inserts=inserts),
              tabla("b", PK, {"nombre": "a_id", "tipo": "integer", "fk": {"tabla": "a"}}))
    validado = validar(e)
    assert validado.cargas["a"] == inserts
    assert "FROM a) AS fk1" in validado.cargas["b"]


def test_tabla_sin_tuplas_no_genera_carga():
    assert validar(espec(tabla("a", PK, {"nombre": "n", "tipo": "text"}, tuplas=0))).cargas["a"] is None
