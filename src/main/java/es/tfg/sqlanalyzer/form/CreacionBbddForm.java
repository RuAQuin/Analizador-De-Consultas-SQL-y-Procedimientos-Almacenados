package es.tfg.sqlanalyzer.form;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/** Datos introducidos en la pantalla "Creación de BBDD" (módulo 1). */
@Getter
@Setter
public class CreacionBbddForm {

    @NotBlank(message = "Indica el nombre de la base de datos")
    @Pattern(regexp = "^[a-z_][a-z0-9_]{0,62}$",
             message = "Solo minúsculas, números y guion bajo; debe empezar por letra o _")
    private String nombreBbdd;

    @NotBlank(message = "Escribe el DDL de creación de las tablas")
    @Size(max = 100000, message = "El DDL es demasiado largo")
    private String definicionTablas;
}
