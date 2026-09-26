package com.example.demo.controller;

import com.example.demo.dto.SavedSchemeResponse;
import com.example.demo.service.SavedSchemeService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/saved")
@RequiredArgsConstructor
public class SavedSchemeController {

    private final SavedSchemeService savedSchemeService;

    @GetMapping
    public List<SavedSchemeResponse> getSavedSchemes(Authentication authentication) {
        return savedSchemeService.getSavedSchemes(authentication.getName());
    }

    @PostMapping("/{schemeId}")
    public String saveScheme(@PathVariable Long schemeId, Authentication authentication) {
        return savedSchemeService.saveScheme(authentication.getName(), schemeId);
    }

    @DeleteMapping("/{schemeId}")
    public String unsaveScheme(@PathVariable Long schemeId, Authentication authentication) {
        return savedSchemeService.unsaveScheme(authentication.getName(), schemeId);
    }
}