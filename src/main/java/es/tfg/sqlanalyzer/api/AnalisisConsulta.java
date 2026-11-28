package es.tfg.sqlanalyzer.api;

import java.io.Serializable;
import java.util.List;

/**
 * Respuesta de la API al análisis de una consulta o procedimiento (módulo 2). Parte 1: el SQL recibido y la BBDD
 * objetivo comprobada. Si no es válida, errores dice por qué (por ejemplo, que la BBDD no es del módulo 1).
 */
public record AnalisisConsulta(boolean valido,
                               List<ErrorDdl> errores,
                               // CONSULTA o PROCEDIMIENTO.
                               String tipo,
                               // BBDD objetivo; null si no se ha elegido (solo análisis estático).
                               String bbdd,
                               // Versión de PostgreSQL del servidor de la BBDD objetivo.
                               String version) implements Serializable {
}
