package es.tfg.sqlanalyzer.api;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.io.Serializable;

/**
 * Tabla del paso 7: lo que sabe PostgreSQL de ella antes y después del ANALYZE.
 * estimadasAntes vale -1 si la tabla nunca se había analizado.
 */
public record TablaAnalizada(String tabla,
                             // Filas pedidas en el prototipo.
                             int filas,
                             // pg_class.reltuples antes y después del ANALYZE.
                             @JsonProperty("estimadas_antes") long estimadasAntes,
                             long estimadas,
                             // pg_class.relpages: páginas de 8 kB.
                             long paginas,
                             // Columnas con estadísticas en pg_stats.
                             int columnas) implements Serializable {

    /** Si el planificador ya conoce el número real de filas. */
    public boolean coincide() {
        return estimadas == filas;
    }
}
