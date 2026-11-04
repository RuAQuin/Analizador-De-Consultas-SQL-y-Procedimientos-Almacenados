package es.tfg.sqlanalyzer.api;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.io.Serializable;
import java.util.List;

/**
 * Posición de un árbol en el orden de carga (paso 2.3, Kahn entre árboles).
 * arboles tiene más de una raíz solo si esos árboles forman un ciclo y se cargan juntos.
 * referencias son las FK que obligan a cargar antes los árboles de dependeDe.
 */
public record GrupoCarga(List<String> arboles,
                         int nivel,
                         @JsonProperty("depende_de") List<String> dependeDe,
                         List<ClaveForanea> referencias) implements Serializable {
}
