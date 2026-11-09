package es.tfg.sqlanalyzer.api;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.io.Serializable;
import java.util.List;

/**
 * Posición de un árbol en el orden de carga (paso 2.3, Kahn entre árboles).
 * referencias son las FK que obligan a cargar antes los árboles de dependeDe.
 */
public record ArbolOrdenado(String raiz,
                            int nivel,
                            @JsonProperty("depende_de") List<String> dependeDe,
                            List<ClaveForanea> referencias) implements Serializable {
}
