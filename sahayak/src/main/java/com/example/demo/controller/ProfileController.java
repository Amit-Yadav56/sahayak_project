package com.example.demo.controller;

import com.example.demo.dto.ProfileRequest;
import com.example.demo.entity.UserProfile;
import com.example.demo.service.UserService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/profile")
@RequiredArgsConstructor
public class ProfileController {

    private final UserService userService;

    @PostMapping
    public String createProfile(Authentication authentication, @RequestBody ProfileRequest request) {
        return userService.createProfile(authentication.getName(), request);
    }

    @GetMapping
    public UserProfile getProfile(Authentication authentication) {
        return userService.getProfile(authentication.getName());
    }

    @PutMapping
    public String updateProfile(Authentication authentication, @RequestBody ProfileRequest request) {
        return userService.updateProfile(authentication.getName(), request);
    }
}