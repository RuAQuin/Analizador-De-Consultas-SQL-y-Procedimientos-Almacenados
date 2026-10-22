package es.tfg.sqlanalyzer.controller;

import org.springframework.stereotype.Controller;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import java.util.Locale;

/** Carga y análisis de logs JPA/Hibernate (.txt). */
@Controller
@RequestMapping("/logs")
public class LogsController {

    @ModelAttribute("activePage")
    // Atributo de modelo que indica la página activa en la navegación.
    public String activePage() {
        return "logs";
    }

    @GetMapping
    // Muestra el formulario de carga de logs. Si no hay un formulario en el modelo, se crea uno nuevo.
    public String formulario() {
        return "logs";
    }

    @PostMapping
    // Procesa la carga de un fichero de logs. Valida el fichero y, si es correcto, redirige a la misma página con un mensaje de aviso.
    public String subir(@RequestParam("fichero") MultipartFile fichero, RedirectAttributes ra) {
        String nombre = StringUtils.cleanPath(
                fichero.getOriginalFilename() == null ? "" : fichero.getOriginalFilename());

        if (fichero.isEmpty()) {
            ra.addFlashAttribute("error", "Selecciona un fichero de logs.");
            return "redirect:/logs";
        }
        if (!nombre.toLowerCase(Locale.ROOT).endsWith(".txt")) {
            ra.addFlashAttribute("error", "Solo se admiten ficheros .txt.");
            return "redirect:/logs";
        }
        // Implementar la invocación a la API Python (extracción y análisis de consultas).
        ra.addFlashAttribute("aviso", "Fichero «" + nombre + "» recibido ("
                + Math.max(1, fichero.getSize() / 1024) + " KB). "
                + "El análisis se realizará cuando la API Python esté conectada.");
        return "redirect:/logs";
    }
}
