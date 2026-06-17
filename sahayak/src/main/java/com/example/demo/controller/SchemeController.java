package com.example.demo.controller;

import com.example.demo.entity.Scheme;
import com.example.demo.service.SchemeService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/schemes")
@RequiredArgsConstructor
public class SchemeController {

    private final SchemeService schemeService;

    @GetMapping
    public List<Scheme> getAllSchemes() {
        return schemeService.getAllSchemes();
    }

    @GetMapping("/{id}")
    public Scheme getSchemeById(
            @PathVariable Long id
    ) {
        return schemeService.getSchemeById(id);
    }

    @GetMapping("/category/{cat}")
    public List<Scheme> getSchemesByCategory(
            @PathVariable String cat
    ) {
        return schemeService.getSchemesByCategory(cat);
    }

    @GetMapping("/search")
    public List<Scheme> searchSchemes(
            @RequestParam String q
    ) {
        return schemeService.searchSchemes(q);
    }
}