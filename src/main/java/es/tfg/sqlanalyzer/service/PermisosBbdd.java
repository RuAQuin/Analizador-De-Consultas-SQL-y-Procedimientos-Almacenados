package es.tfg.sqlanalyzer.service;

import es.tfg.sqlanalyzer.model.BbddPropietario;
import es.tfg.sqlanalyzer.repository.BbddPropietarioRepository;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Set;

/**
 * Qué BBDD del módulo 1 puede ver y usar el usuario conectado.
 * ADMIN y ANALYST: todas. USUARIO: solo las que ha creado él (tabla bbdd_propietarios).
 */
@Service
public class PermisosBbdd {

    private static final Set<String> VEN_TODAS = Set.of("ROLE_ADMIN", "ROLE_ANALYST");

    private final BbddPropietarioRepository repo;

    public PermisosBbdd(BbddPropietarioRepository repo) {
        this.repo = repo;
    }

    /** ADMIN o ANALYST: acceso a todas las BBDD. */
    public boolean veTodas() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        // El usuario conectado tiene algún rol que permite ver todas las BBDD.
        return auth != null && auth.getAuthorities().stream().map(GrantedAuthority::getAuthority).anyMatch(VEN_TODAS::contains);
    }

    /** El usuario conectado puede ver y usar la BBDD «nombre». */
    @Transactional(readOnly = true)
    public boolean puedeUsar(String nombre) {
        if (veTodas()) {
            return true;
        }
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        // El usuario conectado es el propietario de la BBDD «nombre».
        return auth != null && nombre != null && repo.existsByNombreAndUsername(nombre, auth.getName());
    }

    /** Paso 5: la BBDD «nombre» se acaba de crear y su propietario es el usuario conectado. Si había una fila de una
     * BBDD anterior con el mismo nombre (borrada después fuera de la aplicación), se sustituye. */
    @Transactional
    public void registrarPropietario(String nombre) {
        String username = SecurityContextHolder.getContext().getAuthentication().getName();
        BbddPropietario propietario = repo.findByNombre(nombre).orElseGet(() -> new BbddPropietario(nombre, username));
        propietario.setUsername(username);
        repo.save(propietario);
    }
}
