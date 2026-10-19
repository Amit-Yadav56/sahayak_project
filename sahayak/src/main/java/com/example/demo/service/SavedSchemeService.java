package com.example.demo.service;

import com.example.demo.dto.SavedSchemeResponse;
import com.example.demo.entity.*;
import com.example.demo.repository.*;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
public class SavedSchemeService {

    private final SavedSchemeRepository savedSchemeRepository;
    private final UserRepository userRepository;
    private final SchemeRepository schemeRepository;

    public List<SavedSchemeResponse> getSavedSchemes(String email) {
        User user = userRepository.findByEmail(email).orElseThrow(() -> new RuntimeException("User not found"));

        return savedSchemeRepository.findByUser(user).stream()
            .map(saved -> new SavedSchemeResponse(
                saved.getId(),
                saved.getScheme().getId(),
                saved.getScheme().getName(),
                saved.getScheme().getCategory(),
                saved.getScheme().getBenefitAmount(),
                saved.getSavedAt()
            ))
            .toList();
    }

    public String saveScheme(String email, Long schemeId) {
        User user = userRepository.findByEmail(email).orElseThrow(() -> new RuntimeException("User not found"));
        Scheme scheme = schemeRepository.findById(schemeId).orElseThrow(() -> new RuntimeException("Scheme not found"));

        if (savedSchemeRepository.findByUserAndScheme(user, scheme).isPresent()) {
            return "Scheme already saved";
        }

        SavedScheme savedScheme = SavedScheme.builder()
            .user(user)
            .scheme(scheme)
            .savedAt(LocalDateTime.now())
            .build();

        savedSchemeRepository.save(savedScheme);
        return "Scheme saved successfully";
    }

    public String unsaveScheme(String email, Long schemeId) {
        User user = userRepository.findByEmail(email).orElseThrow(() -> new RuntimeException("User not found"));
        Scheme scheme = schemeRepository.findById(schemeId).orElseThrow(() -> new RuntimeException("Scheme not found"));

        SavedScheme savedScheme = savedSchemeRepository.findByUserAndScheme(user, scheme).orElseThrow(() -> new RuntimeException("Saved scheme not found"));

        savedSchemeRepository.delete(savedScheme);
        return "Scheme removed";
    }
}