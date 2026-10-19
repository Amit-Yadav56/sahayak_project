package com.example.demo.controller;

import com.example.demo.dto.*;
import com.example.demo.service.UserService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final UserService userService;

    @PostMapping("/register")
    public org.springframework.http.ResponseEntity<?> register(@Valid @RequestBody RegisterRequest request) {
        String msg = userService.register(request);
        return org.springframework.http.ResponseEntity.ok(java.util.Map.of("message", msg));
    }

    @PostMapping("/login")
    public LoginResponse login(@RequestBody LoginRequest request) {
        return userService.login(request);
    }

    @GetMapping("/me")
    public UserResponse me(Authentication authentication) {
        return userService.getCurrentUser(authentication.getName());
    }

    @PostMapping("/logout")
    public org.springframework.http.ResponseEntity<?> logout() {
        return org.springframework.http.ResponseEntity.ok(java.util.Map.of("message", "Logged out successfully"));
    }
}