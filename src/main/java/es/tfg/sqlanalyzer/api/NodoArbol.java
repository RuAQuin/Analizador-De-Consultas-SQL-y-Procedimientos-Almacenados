package es.tfg.sqlanalyzer.api;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.io.Serializable;

/**
 * Tabla dentro de un árbol de agrupación (paso 2.2).
 * padre y fkAgrupacion son nulos en la raíz. El nivel coincide con la profundidad en el árbol.
 */
public record NodoArbol(String tabla,
                        String padre,
                        int nivel,
                        @JsonProperty("fk_agrupacion") ClaveForanea fkAgrupacion) implements Serializable {

    /** Texto con sangría para dibujar el árbol, p. ej. "   └─ lineas_compra". */
    public String sangria() {
        return nivel == 0 ? tabla : "   ".repeat(nivel - 1) + "└─ " + tabla;
    }
}
