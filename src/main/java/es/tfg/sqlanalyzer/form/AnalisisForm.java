package es.tfg.sqlanalyzer.form;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/** Datos introducidos en la pantalla "Análisis de consultas" (módulo 2). */
@Getter
@Setter
public class AnalisisForm {

    public enum TipoSql { CONSULTA, PROCEDIMIENTO }

    @NotBlank(message = "Introduce la consulta o el procedimiento")
    @Size(max = 50000, message = "El SQL es demasiado largo")
    private String sql;

    @NotNull
    // Tipo de SQL: consulta o procedimiento.
    private TipoSql tipo = TipoSql.CONSULTA;

    // BBDD objetivo del módulo 1 (una de las del desplegable). Vacía: solo análisis estático.
    @Size(max = 63)
    private String bbddDestino;

    // Casilla de verificación para permitir o no el análisis estático (pglast). Por defecto, activada.
    private boolean analisisEstatico = true; 

    // El nivel de EXPLAIN lo decide el sistema (genérico si la consulta tiene parámetros $1, ANALYZE si tiene
    // valores). Esta casilla solo permite negarse a EXPLAIN ANALYZE, que ejecuta de verdad la consulta.
    // Si se desactiva, el sistema hace EXPLAIN sin ANALYZE aunque la consulta tenga valores.
    private boolean permitirAnalyze = true;

    // Casilla de verificación para mostrar o no el SQL formateado. Lo formatea la API con pglast; el SQL se envía tal cual. Por defecto, activada.
    private boolean formatear = true;
}
