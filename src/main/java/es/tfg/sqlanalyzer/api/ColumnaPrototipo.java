package es.tfg.sqlanalyzer.api;

import java.io.Serializable;

/**
 * Columna de una tabla del prototipo (paso 3).
 * origen: "tipo" (valor según su tipo), "fk" (valor de la tabla padre) o "auto" (lo rellena PostgreSQL).
 */
public record ColumnaPrototipo(String nombre, String tipo, String origen) implements Serializable {
}
