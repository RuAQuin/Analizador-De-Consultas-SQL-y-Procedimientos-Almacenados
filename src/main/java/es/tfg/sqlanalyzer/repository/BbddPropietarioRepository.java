package es.tfg.sqlanalyzer.repository;

import es.tfg.sqlanalyzer.model.BbddPropietario;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface BbddPropietarioRepository extends JpaRepository<BbddPropietario, Long> {

    Optional<BbddPropietario> findByNombre(String nombre);

    boolean existsByNombreAndUsername(String nombre, String username);

    // Al renombrar un usuario, sus BBDD pasan al nombre nuevo.
    @Modifying
    @Query("UPDATE BbddPropietario p SET p.username = :nuevo WHERE p.username = :anterior")
    int renombrar(@Param("anterior") String anterior, @Param("nuevo") String nuevo);

    // Al eliminar un usuario: sus BBDD siguen existiendo, pero ya sin propietario (solo ADMIN y ANALYST).
    @Modifying
    @Query("DELETE FROM BbddPropietario p WHERE p.username = :username")
    int borrarDe(@Param("username") String username);
}
