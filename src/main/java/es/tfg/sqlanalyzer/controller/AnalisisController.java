package es.tfg.sqlanalyzer.controller;

import es.tfg.sqlanalyzer.api.AnalisisConsulta;
import es.tfg.sqlanalyzer.api.ApiNoDisponibleException;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.ErrorDdl;
import es.tfg.sqlanalyzer.form.AnalisisForm;
import es.tfg.sqlanalyzer.service.PermisosBbdd;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.util.StringUtils;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

import java.util.List;

/**
 * Módulo 2: análisis de consultas y procedimientos (análisis estático con pglast, Explain Plans, formato SQL y
 * recomendaciones). Parte 1: el SQL y la BBDD objetivo, una de las generadas en el módulo 1.
 * El resultado se muestra en la misma respuesta: no se guarda en la sesión.
 */
@Controller
@RequestMapping("/analisis")
// Controlador para el análisis de consultas SQL y procedimientos almacenados.
public class AnalisisController {

    private final ApiPythonClient api;
    // Qué BBDD puede usar el usuario conectado (USUARIO: solo las suyas).
    private final PermisosBbdd permisos;

    // Constructor que inyecta el cliente de la API y el servicio de permisos de BBDD.
    public AnalisisController(ApiPythonClient api, PermisosBbdd permisos) {
        this.api = api;
        this.permisos = permisos;
    }

    @ModelAttribute("activePage")
    // Atributo de modelo que indica la página activa en la navegación.
    public String activePage() {
        return "analisis";
    }

    @ModelAttribute("tipos")
    // Atributo de modelo que proporciona los tipos de SQL disponibles para el análisis.
    public AnalisisForm.TipoSql[] tipos() {
        return AnalisisForm.TipoSql.values();
    }

    @GetMapping
    // Muestra el formulario de análisis SQL con las BBDD objetivo que puede usar el usuario.
    public String formulario(Model model) {
        if (!model.containsAttribute("form")) {
            model.addAttribute("form", new AnalisisForm());
        }
        model.addAttribute("bbdds", bbddsObjetivo(model));
        return "analisis";
    }

    @PostMapping
    // Envía el SQL a la API con la BBDD objetivo elegida y muestra el resultado en la misma página.
    public String analizar(@Valid @ModelAttribute("form") AnalisisForm form,
                           BindingResult result,
                           Model model) {
        List<String> bbdds = bbddsObjetivo(model);
        model.addAttribute("bbdds", bbdds);

        // Vacía: solo análisis estático. Si no, debe ser una de las del desplegable (el formulario se puede manipular:
        // así un USUARIO no puede analizar una BBDD ajena ni una que no sea del módulo 1).
        String bbdd = StringUtils.hasText(form.getBbddDestino()) ? form.getBbddDestino() : null;
        if (bbdd != null && !bbdds.contains(bbdd)) {
            result.rejectValue("bbddDestino", "bbdd.ajena", "Elige una de tus BBDD objetivo del módulo 1");
        }
        if (result.hasErrors()) {
            return "analisis";
        }

        try {
            // Llama a la API para analizar la consulta o procedimiento SQL con la BBDD objetivo elegida.
            AnalisisConsulta analisis = api.analizarConsulta(form.getSql(), form.getTipo().name(), bbdd);
            model.addAttribute("resultado", analisis);
            model.addAttribute("erroresAnalisis", analisis.errores().stream().map(ErrorDdl::descripcion).toList());
        } catch (ApiNoDisponibleException e) {
            model.addAttribute("error", e.getMessage());
        }
        return "analisis";
    }

    // BBDD objetivo que puede elegir el usuario: las del registro del módulo 1 (paso 8) que están en el servidor de
    // la aplicación (de las restauradas en otro equipo no se guarda la contraseña), que siguen existiendo y que el
    // usuario puede usar (ADMIN y ANALYST, todas; USUARIO, solo las suyas).
    private List<String> bbddsObjetivo(Model model) {
        try {
            return api.listarRegistro().stream()
                    .filter(r -> !StringUtils.hasText(r.servidor())) // Solo las del servidor de la aplicación (no las restauradas en otro equipo).
                    .filter(r -> Boolean.TRUE.equals(r.existe())) // Solo las que siguen existiendo (no se borró la BBDD del servidor).
                    .filter(r -> permisos.puedeUsar(r.nombre())) // Solo las que el usuario puede usar (ADMIN y ANALYST, todas; USUARIO, solo las suyas).
                    .map(r -> r.nombre()) 
                    .toList(); // Devuelve la lista de nombres de BBDD objetivo que puede elegir el usuario.
        } catch (ApiNoDisponibleException e) {
            model.addAttribute("error", "No se han podido leer las BBDD objetivo: " + e.getMessage());
            return List.of();
        }
    }
}
