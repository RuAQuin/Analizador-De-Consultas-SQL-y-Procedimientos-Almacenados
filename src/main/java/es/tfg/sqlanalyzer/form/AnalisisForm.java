package es.tfg.sqlanalyzer.form;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** Datos introducidos en la pantalla "Análisis de consultas" (objetivo 2). */
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

    public String getSql() { return sql; }
    public void setSql(String sql) { this.sql = sql; }
    public TipoSql getTipo() { return tipo; }
    public void setTipo(TipoSql tipo) { this.tipo = tipo; }
    public String getBbddDestino() { return bbddDestino; }
    public void setBbddDestino(String bbddDestino) { this.bbddDestino = bbddDestino; }
    public boolean isAnalisisEstatico() { return analisisEstatico; }
    public void setAnalisisEstatico(boolean analisisEstatico) { this.analisisEstatico = analisisEstatico; }
    public boolean isExplainPlan() { return explainPlan; }
    public void setExplainPlan(boolean explainPlan) { this.explainPlan = explainPlan; }
    public boolean isExplainAnalyze() { return explainAnalyze; }
    public void setExplainAnalyze(boolean explainAnalyze) { this.explainAnalyze = explainAnalyze; }
    public boolean isFormatear() { return formatear; }
    public void setFormatear(boolean formatear) { this.formatear = formatear; }
}
