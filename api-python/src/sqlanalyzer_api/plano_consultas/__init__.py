"""Plano de consultas: análisis de consultas y procedimientos (módulo 2).

Separado del plano de datos (módulo 1), como en el esquema funcional: este plano lee las BBDD objetivo, pero no
las crea ni las modifica.
"""

from .entrada import MAX_SQL, Destino, revisar_destino

__all__ = ["MAX_SQL", "Destino", "revisar_destino"]
