"""Paso 1 · Especificación de la base de datos a generar.

Modelo de lo que el usuario describe en el formulario por pasos de la WebApp:
nombre de la BBDD, tablas, columnas (tipo, nulabilidad, PK, FK, UNQ), número
de tuplas por tabla y, opcionalmente, una distribución de valores por columna.

Aquí solo se valida la *forma* de la petición (nombres, rangos, campos
incompatibles entre sí). Las comprobaciones que dependen del conjunto (que
toda FK apunte a otra tabla existente, tipos, ciclos, sintaxis del DDL con
pglast...) se hacen en :mod:`validacion`.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Mismo patrón que usa la WebApp para el nombre de la BBDD (CreacionBbddForm):
# identificadores en minúsculas que PostgreSQL no necesita entrecomillar.
PATRON_IDENTIFICADOR = r"^[a-z_][a-z0-9_]{0,62}$"

Identificador = Annotated[str, Field(pattern=PATRON_IDENTIFICADOR)]
Limite = int | float | str


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ClaveForanea(_Modelo):
    """Referencia de una columna a la columna de otra tabla."""

    tabla: Identificador
    # Si se omite, se usa la clave primaria (de una sola columna) de la tabla padre.
    columna: Identificador | None = None


class ValorDistribucion(_Modelo):
    """Un valor y el porcentaje de tuplas que lo deben tomar (p. ej. 'ENTREGADO' al 85 %)."""

    valor: Any
    porcentaje: float = Field(gt=0, le=100)


class Columna(_Modelo):
    nombre: Identificador
    tipo: str = Field(min_length=1, max_length=64)
    nulable: bool = False
    pk: bool = False
    unico: bool = False
    # GENERATED ALWAYS AS IDENTITY: la genera PostgreSQL (1..n) y no entra en los INSERT.
    identidad: bool = False
    fk: ClaveForanea | None = None
    # Rango de los valores aleatorios (números o fechas ISO 'AAAA-MM-DD').
    minimo: Limite | None = None
    maximo: Limite | None = None
    porcentaje_nulos: float = Field(default=0, ge=0, le=100)
    distribucion: list[ValorDistribucion] | None = None

    @property
    def es_unica(self) -> bool:
        return self.pk or self.unico

    @model_validator(mode="after")
    def _coherencia(self) -> Columna:
        if self.pk and self.nulable:
            raise ValueError(f"'{self.nombre}': una columna PK no puede ser nulable")
        if self.porcentaje_nulos and not self.nulable:
            raise ValueError(f"'{self.nombre}': porcentaje_nulos exige nulable=true")
        if self.identidad and (self.fk or self.distribucion):
            raise ValueError(f"'{self.nombre}': una columna identidad no admite fk ni distribucion")
        if self.distribucion is not None:
            if not self.distribucion:
                raise ValueError(f"'{self.nombre}': la distribución está vacía")
            if self.es_unica or self.fk:
                raise ValueError(f"'{self.nombre}': no se admite distribución en columnas PK, UNQ o FK")
            total = sum(v.porcentaje for v in self.distribucion)
            if total > 100 + 1e-9:
                raise ValueError(f"'{self.nombre}': la distribución suma {total:g} % (máximo 100 %)")
        return self


class Tabla(_Modelo):
    nombre: Identificador
    tuplas: int = Field(default=0, ge=0)
    columnas: list[Columna] = Field(min_length=1)
    # INSERTs aportados por el usuario: si llegan, sustituyen a la generación aleatoria.
    inserts: str | None = None

    @property
    def clave_primaria(self) -> list[Columna]:
        return [c for c in self.columnas if c.pk]

    def columna(self, nombre: str) -> Columna | None:
        return next((c for c in self.columnas if c.nombre == nombre), None)

    @model_validator(mode="after")
    def _columnas_unicas(self) -> Tabla:
        nombres = [c.nombre for c in self.columnas]
        repetidas = sorted({n for n in nombres if nombres.count(n) > 1})
        if repetidas:
            raise ValueError(f"tabla '{self.nombre}': columnas repetidas {repetidas}")
        return self


class EspecificacionBbdd(_Modelo):
    nombre: Identificador
    tablas: list[Tabla] = Field(min_length=1)
    # Semilla opcional de random() (setseed) para que la carga sea reproducible.
    semilla: float | None = Field(default=None, ge=-1, le=1)

    def tabla(self, nombre: str) -> Tabla | None:
        return next((t for t in self.tablas if t.nombre == nombre), None)

    def destino_fk(self, columna: Columna) -> tuple[Tabla, Columna] | None:
        """Tabla y columna padre a las que apunta la FK de ``columna`` (None si no existen)."""
        padre = self.tabla(columna.fk.tabla) if columna.fk else None
        if padre is None:
            return None
        if columna.fk.columna is not None:
            referenciada = padre.columna(columna.fk.columna)
        else:
            pk = padre.clave_primaria
            referenciada = pk[0] if len(pk) == 1 else None
        return (padre, referenciada) if referenciada else None

    @model_validator(mode="after")
    def _tablas_unicas(self) -> EspecificacionBbdd:
        nombres = [t.nombre for t in self.tablas]
        repetidas = sorted({n for n in nombres if nombres.count(n) > 1})
        if repetidas:
            raise ValueError(f"tablas repetidas {repetidas}")
        return self
