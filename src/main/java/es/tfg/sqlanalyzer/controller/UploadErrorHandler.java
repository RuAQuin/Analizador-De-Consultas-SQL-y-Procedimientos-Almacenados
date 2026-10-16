package es.tfg.sqlanalyzer.controller;

import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@ControllerAdvice
public class UploadErrorHandler {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public String ficheroDemasiadoGrande(RedirectAttributes ra) {
        ra.addFlashAttribute("error", "El fichero supera el tamaño máximo permitido (20 MB).");
        return "redirect:/logs";
    }
}
