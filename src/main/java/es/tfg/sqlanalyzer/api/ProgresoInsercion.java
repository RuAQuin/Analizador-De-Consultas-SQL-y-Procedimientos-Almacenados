package es.tfg.sqlanalyzer.api;

/**
 * Cómo va la inserción en marcha (paso 6), para el reloj de la carga.
 * Primero se generan las tuplas (fase «generando») y después se escriben tabla a tabla (fase «escribiendo»).
 * En cada fase, hechas va de 0 a total (las filas de todas las tablas).
 */
public record ProgresoInsercion(String fase, // "generando" o "escribiendo"
                                // Tabla que se está escribiendo (null mientras se generan las tuplas).
                                String tabla,
                                long hechas, // Filas ya generadas o ya escritas.
                                long total) {
}
