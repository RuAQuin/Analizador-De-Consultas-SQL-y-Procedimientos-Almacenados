package es.tfg.sqlanalyzer.api;

import java.io.Serializable;

/** Posición de una tabla en el orden topológico de Kahn (paso 2.1). Nivel 0 = sin padres. */
public record TablaOrdenada(String tabla, int nivel) implements Serializable {
}
