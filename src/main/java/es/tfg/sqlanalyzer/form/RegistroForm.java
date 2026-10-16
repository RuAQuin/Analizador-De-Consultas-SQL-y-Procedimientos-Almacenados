package es.tfg.sqlanalyzer.form;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** Datos introducidos en la pantalla de registro de una nueva cuenta. */
public class RegistroForm {

    @NotBlank(message = "Indica un nombre de usuario")
    @Pattern(regexp = "^[a-zA-Z0-9_.-]{3,50}$",
             message = "Solo letras, números, punto, guion y guion bajo (3-50 caracteres)")
    private String username;

    @NotBlank(message = "Indica una contraseña")
    @Size(min = 6, max = 72, message = "La contraseña debe tener entre 6 y 72 caracteres")
    private String password;

    @NotBlank(message = "Repite la contraseña")
    private String confirmPassword;

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
    public String getConfirmPassword() { return confirmPassword; }
    public void setConfirmPassword(String confirmPassword) { this.confirmPassword = confirmPassword; }
}
