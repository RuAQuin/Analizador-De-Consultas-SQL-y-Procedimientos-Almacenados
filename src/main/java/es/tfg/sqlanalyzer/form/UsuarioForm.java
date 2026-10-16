package es.tfg.sqlanalyzer.form;

import es.tfg.sqlanalyzer.model.Rol;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** Datos del formulario de alta/edición de usuarios (gestión por el administrador). */
public class UsuarioForm {

    private Long id;

    @NotBlank(message = "Indica un nombre de usuario")
    @Pattern(regexp = "^[a-zA-Z0-9_.-]{3,50}$",
             message = "Solo letras, números, punto, guion y guion bajo (3-50 caracteres)")
    private String username;

    @Size(max = 72, message = "La contraseña debe tener como máximo 72 caracteres")
    private String password;

    @NotNull(message = "Selecciona un rol")
    private Rol rol = Rol.ANALYST;

    private boolean habilitado = true;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
    public Rol getRol() { return rol; }
    public void setRol(Rol rol) { this.rol = rol; }
    public boolean isHabilitado() { return habilitado; }
    public void setHabilitado(boolean habilitado) { this.habilitado = habilitado; }
}
