"""Plano de datos · Módulo 1: generación de BBDD."""

from .especificacion import EspecificacionBbdd
from .generador import ResultadoGeneracion, generar_bbdd
from .validacion import ErrorValidacion, ScriptValidado, validar

__all__ = ["EspecificacionBbdd", "ErrorValidacion", "ResultadoGeneracion", "ScriptValidado",
           "generar_bbdd", "validar"]
