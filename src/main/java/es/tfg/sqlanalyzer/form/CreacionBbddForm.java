package es.tfg.sqlanalyzer.form;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** Datos introducidos en la pantalla "Creación de BBDD" (objetivo 1). */
public class CreacionBbddForm {

    @NotBlank(message = "Indica el nombre de la base de datos")
    @Pattern(regexp = "^[a-z_][a-z0-9_]{0,62}$",
             message = "Solo minúsculas, números y guion bajo; debe empezar por letra o _")
    private String nombreBbdd;

    @NotBlank(message = "Define al menos una tabla")
    @Size(max = 20000, message = "La definición es demasiado larga")
    private String definicionTablas;

    @Size(max = 2000, message = "La petición es demasiado larga")
    private String peticionDatos;

    @Min(value = 0, message = "Mínimo 0 filas")
    @Max(value = 100000, message = "Máximo 100.000 filas por tabla")
    private int filasPorTabla = 100;

    private boolean exportarPgDump = true;

    public String getNombreBbdd() { return nombreBbdd; }
    public void setNombreBbdd(String nombreBbdd) { this.nombreBbdd = nombreBbdd; }
    public String getDefinicionTablas() { return definicionTablas; }
    public void setDefinicionTablas(String definicionTablas) { this.definicionTablas = definicionTablas; }
    public String getPeticionDatos() { return peticionDatos; }
    public void setPeticionDatos(String peticionDatos) { this.peticionDatos = peticionDatos; }
    public int getFilasPorTabla() { return filasPorTabla; }
    public void setFilasPorTabla(int filasPorTabla) { this.filasPorTabla = filasPorTabla; }
    public boolean isExportarPgDump() { return exportarPgDump; }
    public void setExportarPgDump(boolean exportarPgDump) { this.exportarPgDump = exportarPgDump; }
}
