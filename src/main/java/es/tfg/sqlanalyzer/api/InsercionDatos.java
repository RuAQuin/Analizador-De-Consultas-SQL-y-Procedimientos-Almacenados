package es.tfg.sqlanalyzer.api;

import java.io.Serializable;
import java.util.List;

/**
 * Respuesta de la API a la inserción de datos (paso 6): las tuplas se generan siguiendo el diagrama
 * (árbol a árbol y en profundidad) y se escriben tabla a tabla en el orden de Kahn.
 * Si no es válida, errores dice por qué (por ejemplo, la fila que incumple un CHECK) y no se ha insertado nada.
 */
public record InsercionDatos(boolean valido,
                             List<ErrorDdl> errores,
                             String bbdd,
                             // En el orden en que se han escrito (Kahn).
                             List<TablaInsertada> tablas,
                             // Tiempo de la generación y la escritura.
                             double segundos) implements Serializable {

    /** Filas insertadas en total. */
    public int totalFilas() {
        return tablas.stream().mapToInt(TablaInsertada::filas).sum();
    }
}
