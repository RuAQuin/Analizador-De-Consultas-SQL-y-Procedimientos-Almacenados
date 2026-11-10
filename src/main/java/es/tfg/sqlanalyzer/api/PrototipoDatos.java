package es.tfg.sqlanalyzer.api;

import java.io.Serializable;
import java.util.List;

/**
 * Respuesta de la API al prototipo de datos (paso 3).
 * Si no es válido, errores contiene los avisos de coherencia y tablas está vacía.
 */
public record PrototipoDatos(boolean valido,
                             List<ErrorDdl> errores,
                             // En el orden de Kahn de las tablas (paso 2.1).
                             List<TablaPrototipo> tablas) implements Serializable {
}
