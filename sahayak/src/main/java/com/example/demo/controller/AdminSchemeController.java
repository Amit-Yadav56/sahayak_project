package com.example.demo.controller;

import com.example.demo.dto.SchemeRequest;
import com.example.demo.entity.Scheme;
import com.example.demo.service.SchemeService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/admin/schemes")
@RequiredArgsConstructor
public class AdminSchemeController {

    private final SchemeService schemeService;

    @PostMapping
    public Scheme createScheme(@RequestBody SchemeRequest request) {
        return schemeService.createScheme(request);
    }

    @PutMapping("/{id}")
    public Scheme updateScheme(@PathVariable Long id, @RequestBody SchemeRequest request) {
        return schemeService.updateScheme(id, request);
    }
}