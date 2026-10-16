package es.tfg.sqlanalyzer.controller;

import es.tfg.sqlanalyzer.form.RegistroForm;
import es.tfg.sqlanalyzer.service.UsuarioService;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

/** Registro público de nuevas cuentas (siempre con rol ANALYST). */
@Controller
public class RegistroController {

    private final UsuarioService usuarioService;

    public RegistroController(UsuarioService usuarioService) {
        this.usuarioService = usuarioService;
    }

    @GetMapping("/registro")
    public String formulario(Model model) {
        if (!model.containsAttribute("form")) {
            model.addAttribute("form", new RegistroForm());
        }
        return "registro";
    }

    @PostMapping("/registro")
    public String registrar(@Valid @ModelAttribute("form") RegistroForm form,
                             BindingResult result,
                             RedirectAttributes ra) {
        if (form.getPassword() != null && !form.getPassword().equals(form.getConfirmPassword())) {
            result.rejectValue("confirmPassword", "mismatch", "Las contraseñas no coinciden");
        }
        if (!result.hasFieldErrors("username") && usuarioService.existeUsername(form.getUsername())) {
            result.rejectValue("username", "duplicado", "Ese nombre de usuario ya está en uso");
        }
        if (result.hasErrors()) {
            return "registro";
        }

        usuarioService.registrar(form.getUsername(), form.getPassword());
        ra.addFlashAttribute("aviso", "Cuenta creada correctamente. Ya puedes iniciar sesión.");
        return "redirect:/login";
    }
}
