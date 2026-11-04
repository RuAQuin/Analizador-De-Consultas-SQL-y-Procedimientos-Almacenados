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
                            List<String> tablas,
                            List<ErrorDdl> errores,
                            @JsonProperty("claves_foraneas") List<ClaveForanea> clavesForaneas,
                            List<TablaOrdenada> orden,
                            @JsonProperty("tablas_intermedias") List<TablaIntermedia> tablasIntermedias,
                            @JsonProperty("ddl_final") String ddlFinal,
                            List<Arbol> arboles) {
}
