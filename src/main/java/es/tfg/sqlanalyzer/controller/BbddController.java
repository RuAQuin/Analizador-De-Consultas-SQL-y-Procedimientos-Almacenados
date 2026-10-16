package es.tfg.sqlanalyzer.controller;

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

/** Objetivo 1: generación de BBDD, inserción de datos y exportación con pg_dump. */
@Controller
@RequestMapping("/bbdd")
public class BbddController {

    @ModelAttribute("activePage")
    public String activePage() {
        return "bbdd";
    }

    @GetMapping
    public String formulario(Model model) {
        if (!model.containsAttribute("form")) {
            model.addAttribute("form", new CreacionBbddForm());
        }
        return "bbdd";
    }

    @PostMapping
    public String crear(@Valid @ModelAttribute("form") CreacionBbddForm form,
                        BindingResult result,
                        RedirectAttributes ra) {
        if (result.hasErrors()) {
            return "bbdd";
        }
        // TODO: invocar a la API Python (generación, inserción y pg_dump).
        ra.addFlashAttribute("form", form);
        ra.addFlashAttribute("aviso",
                "Petición validada. La generación de «" + form.getNombreBbdd()
                + "» se realizará cuando la API Python esté conectada.");
        return "redirect:/bbdd";
    }
}
