package es.tfg.sqlanalyzer.controller;

import es.tfg.sqlanalyzer.api.ApiNoDisponibleException;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.ErrorDdl;
import es.tfg.sqlanalyzer.api.ValidacionDdl;
import es.tfg.sqlanalyzer.form.CreacionBbddForm;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

/** Módulo 1: generación de BBDD. */
@Controller
@RequestMapping("/bbdd")
public class BbddController {

    private final ApiPythonClient api;

    public BbddController(ApiPythonClient api) {
        this.api = api;
    }

    @ModelAttribute("activePage")
    // Atributo de modelo que indica la página activa en la navegación.
    public String activePage() {
        return "bbdd";
    }

    @GetMapping
    // Muestra el formulario de creación de BBDD. Si no hay un formulario en el modelo, se crea uno nuevo.
    public String formulario(Model model) {
        if (!model.containsAttribute("form")) {
            model.addAttribute("form", new CreacionBbddForm());
        }
        return "bbdd";
    }

    @PostMapping
    // Paso 1: la API parsea el DDL con pglast. Si falla, se vuelve al formulario
    // con el DDL escrito y los errores, para que el usuario lo corrija.
    public String validarDdl(@Valid @ModelAttribute("form") CreacionBbddForm form,
                             BindingResult result,
                             Model model,
                             RedirectAttributes ra) {
        if (result.hasErrors()) {
            return "bbdd";
        }

        ValidacionDdl validacion;
        try {
            validacion = api.validarDdl(form.getDefinicionTablas());
        } catch (ApiNoDisponibleException e) {
            model.addAttribute("error", e.getMessage());
            return "bbdd";
        }

        if (!validacion.valido()) {
            for (ErrorDdl error : validacion.errores()) {
                result.rejectValue("definicionTablas", "ddl.invalido", error.descripcion());
            }
            return "bbdd";
        }

        ra.addFlashAttribute("form", form);
        ra.addFlashAttribute("tablas", validacion.tablas());
        ra.addFlashAttribute("aviso", "El DDL es correcto: pglast lo ha parseado sin errores.");
        return "redirect:/bbdd";
    }
}
