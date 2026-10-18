"""Configuración de la conexión al PostgreSQL objetivo, leída de variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConfigPostgres:
    host: str = "localhost"
    puerto: int = 5432
    usuario: str = "postgres"
    contrasena: str = ""
    # BBDD a la que se conecta para ejecutar CREATE/DROP DATABASE.
    bd_mantenimiento: str = "postgres"
    # Repositorio de análisis: separado de las BBDD objetivo (aquí se registran las BBDD).
    bd_repositorio: str = "sqlanalyzer_repositorio"
    pg_dump: str = "pg_dump"
    directorio_dumps: Path = Path("dumps")

    @classmethod
    def desde_entorno(cls) -> ConfigPostgres:
        e = os.environ
        return cls(
            host=e.get("PG_HOST", cls.host),
            puerto=int(e.get("PG_PUERTO", cls.puerto)),
            usuario=e.get("PG_USUARIO", cls.usuario),
            contrasena=e.get("PG_CONTRASENA", cls.contrasena),
            bd_mantenimiento=e.get("PG_BD_MANTENIMIENTO", cls.bd_mantenimiento),
            bd_repositorio=e.get("PG_BD_REPOSITORIO", cls.bd_repositorio),
            pg_dump=e.get("PG_DUMP", cls.pg_dump),
            directorio_dumps=Path(e.get("DIRECTORIO_DUMPS", cls.directorio_dumps)),
        )

    def conexion(self, bd: str) -> dict:
        """Parámetros de psycopg.connect() para la base de datos ``bd``."""
        return {"host": self.host, "port": self.puerto, "user": self.usuario,
                "password": self.contrasena, "dbname": bd}

    def url(self, bd: str) -> str:
        """Enlace de conexión sin contraseña (el que se guarda en el registro)."""
        return f"postgresql://{self.usuario}@{self.host}:{self.puerto}/{bd}"
