package es.tfg.sqlanalyzer.form;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/** Datos introducidos en la pantalla "Análisis de consultas" (objetivo 2). */
@Getter
@Setter
public class AnalisisForm {

    public enum TipoSql { CONSULTA, PROCEDIMIENTO }

    @NotBlank(message = "Introduce la consulta o el procedimiento")
    @Size(max = 50000, message = "El SQL es demasiado largo")
    private String sql;

    @NotNull
    private TipoSql tipo = TipoSql.CONSULTA;

    @Size(max = 63)
    private String bbddDestino;

    private boolean analisisEstatico = true;
    private boolean explainPlan = true;
    private boolean explainAnalyze = false;
    private boolean formatear = true;
}
