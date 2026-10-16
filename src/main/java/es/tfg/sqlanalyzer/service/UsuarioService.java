package es.tfg.sqlanalyzer.service;

import es.tfg.sqlanalyzer.form.UsuarioForm;
import es.tfg.sqlanalyzer.model.Rol;
import es.tfg.sqlanalyzer.model.Usuario;
import es.tfg.sqlanalyzer.repository.UsuarioRepository;
import org.springframework.data.domain.Sort;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import java.util.List;

/** CRUD de usuarios y alta de cuentas (registro público). */
@Service
public class UsuarioService {

    private final UsuarioRepository repo;
    private final PasswordEncoder encoder;

    public UsuarioService(UsuarioRepository repo, PasswordEncoder encoder) {
        this.repo = repo;
        this.encoder = encoder;
    }

    @Transactional(readOnly = true)
    public List<Usuario> listarTodos() {
        return repo.findAll(Sort.by("username"));
    }

    @Transactional(readOnly = true)
    public Usuario obtener(Long id) {
        return repo.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Usuario no encontrado"));
    }

    @Transactional(readOnly = true)
    public boolean existeUsername(String username) {
        return repo.existsByUsername(username);
    }

    @Transactional(readOnly = true)
    public boolean existeUsernameDeOtro(Long id, String username) {
        return repo.existsByUsernameAndIdNot(username, id);
    }

    /** Registro público: siempre crea una cuenta ANALYST habilitada. */
    @Transactional
    public Usuario registrar(String username, String rawPassword) {
        Usuario usuario = new Usuario();
        usuario.setUsername(username);
        usuario.setPassword(encoder.encode(rawPassword));
        usuario.setRol(Rol.ANALYST);
        usuario.setHabilitado(true);
        return repo.save(usuario);
    }

    @Transactional
    public Usuario crear(UsuarioForm form) {
        Usuario usuario = new Usuario();
        usuario.setUsername(form.getUsername());
        usuario.setPassword(encoder.encode(form.getPassword()));
        usuario.setRol(form.getRol());
        usuario.setHabilitado(form.isHabilitado());
        return repo.save(usuario);
    }

    @Transactional
    public Usuario actualizar(Long id, UsuarioForm form) {
        Usuario usuario = obtener(id);

        if (usuario.getRol() == Rol.ADMIN && form.getRol() != Rol.ADMIN && esUltimoAdmin(usuario)) {
            throw new IllegalStateException("No se puede quitar el rol ADMIN al último administrador.");
        }
        if (usuario.getRol() == Rol.ADMIN && !form.isHabilitado() && esUltimoAdmin(usuario)) {
            throw new IllegalStateException("No se puede deshabilitar al último administrador.");
        }

        usuario.setUsername(form.getUsername());
        if (StringUtils.hasText(form.getPassword())) {
            usuario.setPassword(encoder.encode(form.getPassword()));
        }
        usuario.setRol(form.getRol());
        usuario.setHabilitado(form.isHabilitado());
        return repo.save(usuario);
    }

    @Transactional
    public void eliminar(Long id) {
        Usuario usuario = obtener(id);
        if (usuario.getRol() == Rol.ADMIN && esUltimoAdmin(usuario)) {
            throw new IllegalStateException("No se puede eliminar al último administrador.");
        }
        repo.delete(usuario);
    }

    private boolean esUltimoAdmin(Usuario usuario) {
        return usuario.getRol() == Rol.ADMIN && repo.countByRol(Rol.ADMIN) <= 1;
    }
}
