package es.tfg.sqlanalyzer.controller;

import es.tfg.sqlanalyzer.form.AnalisisForm;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

/**
 * Objetivo 2: análisis estático (pglast), Explain Plans, formato SQL y
 * recomendaciones de optimización.
 */
@Controller
@RequestMapping("/analisis")
public class AnalisisController {

    @ModelAttribute("activePage")
    public String activePage() {
        return "analisis";
    }

    @ModelAttribute("tipos")
    public AnalisisForm.TipoSql[] tipos() {
        return AnalisisForm.TipoSql.values();
    }

    @GetMapping
    public String formulario(Model model) {
        if (!model.containsAttribute("form")) {
            model.addAttribute("form", new AnalisisForm());
        }
        return "analisis";
    }

    @PostMapping
    public String analizar(@Valid @ModelAttribute("form") AnalisisForm form,
                           BindingResult result,
                           RedirectAttributes ra) {
        if (form.isExplainAnalyze() && !form.isExplainPlan()) {
            result.rejectValue("explainAnalyze", "explain",
                    "EXPLAIN ANALYZE requiere activar el Explain Plan");
        }
        if (result.hasErrors()) {
            return "analisis";
        }
        // TODO: invocar a la API Python (pglast + EXPLAIN) y pintar resultados.
        ra.addFlashAttribute("form", form);
        ra.addFlashAttribute("aviso",
                "Petición validada. Los resultados del análisis aparecerán aquí cuando la API Python esté conectada.");
        return "redirect:/analisis";
    }
}
