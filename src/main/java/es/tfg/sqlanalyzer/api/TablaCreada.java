package es.tfg.sqlanalyzer.api;

import java.io.Serializable;

/** Tabla creada en el paso 5 con el CREATE TABLE que se ha ejecutado. */
public record TablaCreada(String tabla, String sentencia) implements Serializable {
}
