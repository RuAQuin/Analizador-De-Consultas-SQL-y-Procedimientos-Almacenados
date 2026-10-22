package es.tfg.sqlanalyzer.controller;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class HomeController {

    @GetMapping("/login")
    // Muestra la página de login.
    public String login() {
        return "login";
    }

    @GetMapping("/")
    // Muestra la página de inicio (dashboard) y establece la página activa en el modelo.
    public String dashboard(Model model) {
        model.addAttribute("activePage", "inicio");
        return "dashboard";
    }

    @GetMapping("/acceso-denegado")
    // Muestra la página de acceso denegado cuando un usuario intenta acceder a un recurso sin los permisos necesarios.
    public String accesoDenegado() {
        return "acceso-denegado";
    }
}
