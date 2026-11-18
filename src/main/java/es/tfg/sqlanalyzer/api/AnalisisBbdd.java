package es.tfg.sqlanalyzer.api;

import java.io.Serializable;
import java.util.List;

/**
 * Respuesta de la API al ANALYZE (paso 7), que cierra la carga: el planificador de PostgreSQL pasa a tener
 * estadísticas reales de los datos insertados en el paso 6.
 * Si no es válida, errores dice por qué (por ejemplo, que los datos aún no se han insertado).
 */
public record AnalisisBbdd(boolean valido,
                           List<ErrorDdl> errores,
                           String bbdd,
                           // En el orden en que se han analizado (Kahn).
                           List<TablaAnalizada> tablas,
                           double segundos) implements Serializable {
}
