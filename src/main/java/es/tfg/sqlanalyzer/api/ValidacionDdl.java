package es.tfg.sqlanalyzer.api;

import java.util.List;

/** Respuesta de la API al paso 1 del módulo 1 (parseo del DDL con pglast). */
public record ValidacionDdl(boolean valido, List<String> tablas, List<ErrorDdl> errores) {
}
