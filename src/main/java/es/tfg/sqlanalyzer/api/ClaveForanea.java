package es.tfg.sqlanalyzer.api;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.io.Serializable;
import java.util.List;

/** FK leída del DDL por la API (paso 2.1). */
public record ClaveForanea(String tabla,
                           List<String> columnas,
                           @JsonProperty("tabla_padre") String tablaPadre,
                           // Vacía si el DDL no las indica: referencia la PK de la tabla padre.
                           @JsonProperty("columnas_padre") List<String> columnasPadre) implements Serializable {

    /** Texto para mostrar, p. ej. "compras (cliente_id) → clientes (id)". */
    public String descripcion() {
        String padre = columnasPadre == null || columnasPadre.isEmpty() ? "PK" : String.join(", ", columnasPadre);
        return tabla + " (" + String.join(", ", columnas) + ") → " + tablaPadre + " (" + padre + ")";
    }
}
