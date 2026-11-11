package es.tfg.sqlanalyzer.api;

import java.io.Serializable;
import java.util.List;

/**
 * Respuesta de la API al confirmar la creación (pasos 4 y 5): CREATE DATABASE y CREATE TABLE.
 * Si no es válida, errores dice por qué (nombre reservado o ya existente, fallo de un CREATE TABLE...)
 * y no se ha creado nada.
 */
public record CreacionBbdd(boolean valido,
                           List<ErrorDdl> errores,
                           String bbdd,
                           // Esquemas creados antes de las tablas (CREATE TABLE ventas.clientes).
                           List<String> esquemas,
                           // En el orden en que se han creado (Kahn).
                           List<TablaCreada> tablas) implements Serializable {
}
