package es.tfg.sqlanalyzer.api;

import java.io.Serializable;

/** Tabla del paso 6 con el número de filas insertadas. */
public record TablaInsertada(String tabla, int filas) implements Serializable {
}
