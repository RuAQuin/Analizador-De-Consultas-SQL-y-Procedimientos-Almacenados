package es.tfg.sqlanalyzer.api;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

/**
 * Respuesta de la API al validar el DDL.
 * Paso 1: parseo con pglast (valido, tablas, errores).
 * Paso 2.1: FK leídas del DDL y orden topológico de Kahn.
 * Paso 2.2: árboles de agrupación (cada tabla cuelga de su FK de agrupación).
 * Paso 2.3: orden de carga de los árboles (Kahn entre árboles).
 * Los ciclos (entre tablas o entre árboles) llegan como errores.
 */
public record ValidacionDdl(boolean valido,
                            // Paso 1: tablas leídas del DDL.
                            List<String> tablas,
                            // Errores: sintaxis del DDL, FK a tablas inexistentes, ciclos, etc.
                            List<ErrorDdl> errores,
                            // Paso 2.1: FK leídas del DDL y orden topológico de Kahn.
                            // JSONProperty para modificar el nombre de la propiedad en el JSON, que por defecto sería "clavesForaneas" (camelCase) y queremos que sea "claves_foraneas" (snake_case).
                            @JsonProperty("claves_foraneas") List<ClaveForanea> clavesForaneas,
                            List<TablaOrdenada> orden,
                            // Paso 2.2: árboles de agrupación (cada tabla cuelga de su FK de agrupación).
                            List<Arbol> arboles,
                            // Paso 2.3: orden de carga de los árboles (Kahn entre árboles).
                            @JsonProperty("orden_carga") List<ArbolOrdenado> ordenCarga) {
}
