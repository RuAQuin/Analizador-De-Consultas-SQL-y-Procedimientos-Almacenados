package es.tfg.sqlanalyzer.api;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

/**
 * Respuesta de la API al validar el DDL.
 * Paso 1: parseo con pglast (valido, tablas, errores).
 * Paso 2.1: FK leídas del DDL y orden topológico de Kahn. Si las FK formaban un ciclo,
 * la API lo rompe con tablas intermedias y devuelve el DDL resultante en ddlFinal.
 * Paso 2.2: árboles de agrupación (cada tabla cuelga de su FK de agrupación).
 */
public record ValidacionDdl(boolean valido,
                            // Paso 1: tablas leídas del DDL.
                            List<String> tablas,
                            // Paso 1: errores de sintaxis del DDL, FK a tablas inexistentes, etc.
                            List<ErrorDdl> errores,
                            // Paso 2.1: FK leídas del DDL y orden topológico de Kahn.
                            // JSONProperty para modificar el nombre de la propiedad en el JSON, que por defecto sería "clavesForaneas" (camelCase) y queremos que sea "claves_foraneas" (snake_case).
                            @JsonProperty("claves_foraneas") List<ClaveForanea> clavesForaneas,
                            List<TablaOrdenada> orden,
                            // Paso 2.1: tablas intermedias creadas para romper ciclos de FK.
                            @JsonProperty("tablas_intermedias") List<TablaIntermedia> tablasIntermedias,
                            // Paso 2.1: DDL final tras romper ciclos de FK con tablas intermedias.
                            @JsonProperty("ddl_final") String ddlFinal,
                            // Paso 2.2: árboles de agrupación (cada tabla cuelga de su FK de agrupación).
                            List<Arbol> arboles,
                            // Paso 2.3: orden de carga de los árboles (Kahn entre árboles).
                            @JsonProperty("orden_carga") List<GrupoCarga> ordenCarga) {
}
