package com.example.demo.controller;

import com.example.demo.dto.ParseUrlRequest;
import com.example.demo.entity.Scheme;
import com.example.demo.entity.User;
import com.example.demo.entity.UserProfile;
import com.example.demo.repository.UserProfileRepository;
import com.example.demo.repository.UserRepository;
import com.example.demo.service.MlService;
import com.example.demo.service.SchemeService;
import com.fasterxml.jackson.databind.JsonNode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/schemes")
@RequiredArgsConstructor
public class SchemeController {

    private final SchemeService schemeService;
    private final MlService mlService;
    private final UserProfileRepository profileRepository;
    private final UserRepository userRepository;

    @GetMapping
    public List<Scheme> getAllSchemes() {
        return schemeService.getAllSchemes();
    }

    @GetMapping("/{id}")
    public Scheme getSchemeById(@PathVariable Long id) {
        return schemeService.getSchemeById(id);
    }

    @GetMapping("/category/{cat}")
    public List<Scheme> getSchemesByCategory(@PathVariable String cat) {
        return schemeService.getSchemesByCategory(cat);
    }

    @GetMapping("/search")
    public List<Scheme> searchSchemes(@RequestParam String q) {
        return schemeService.searchSchemes(q);
    }

    @GetMapping("/semantic-search")
    public ResponseEntity<?> semanticSearch(
            @RequestParam String q,
            @RequestParam(defaultValue = "en") String language,
            @RequestParam(defaultValue = "10") int topK
    ) {
        return ResponseEntity.ok(schemeService.semanticSearch(q, language, topK));
    }

    @GetMapping("/my")
    public ResponseEntity<?> getMySchemes(
            Authentication authentication,
            @RequestParam(defaultValue = "20") int topN,
            @RequestParam(defaultValue = "LIKELY_ELIGIBLE") String minStatus
    ) {
        User currentUser = userRepository.findByEmail(authentication.getName())
                .orElseThrow(() -> new RuntimeException("Authenticated user not found: " + authentication.getName()));

        UserProfile profile = profileRepository.findByUser(currentUser)
                .orElseThrow(() -> new ProfileNotFoundException("No profile found for user " + currentUser.getId() + ". Complete your profile first."));

        log.info("Matching schemes for user={} state={} caste={}",
                currentUser.getId(),
                profile.getUser() != null ? profile.getUser().getState() : "",
                profile.getCasteCategory());

        JsonNode mlResult = mlService.matchSchemes(profile, topN, minStatus);
        return ResponseEntity.ok(mlResult);
    }

    @PostMapping("/admin/parse-url")
    public ResponseEntity<?> parseUrl(@RequestBody ParseUrlRequest request) {
        String url = request.getUrl();
        String stateHint = request.getStateHint() != null ? request.getStateHint() : "any";

        String eligibilityText;
        try {
            log.info("Fetching scheme URL: {}", url);
            Document doc = Jsoup.connect(url)
                    .userAgent("Mozilla/5.0")
                    .timeout(10000)
                    .get();

            String sectionText = doc.select("[data-tab=eligibility], .eligibility-section, #eligibility").text();
            eligibilityText = sectionText.isBlank() ? doc.body().text() : sectionText;

            if (eligibilityText.length() > 3000) {
                eligibilityText = eligibilityText.substring(0, 3000);
            }
        } catch (IOException e) {
            log.error("Failed to fetch URL {}: {}", url, e.getMessage());
            return ResponseEntity.badRequest().body(Map.of("error", "Could not fetch URL: " + e.getMessage()));
        }

        if (eligibilityText.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "No extractable text found at URL"));
        }

        log.info("Extracting criteria from {} chars of text", eligibilityText.length());
        JsonNode mlResult = mlService.extractCriteria(eligibilityText, stateHint);

        return ResponseEntity.ok(Map.of(
                "url", url,
                "extracted_text_length", eligibilityText.length(),
                "eligibility_json", mlResult.get("eligibility_json"),
                "elapsed_ms", mlResult.get("elapsed_ms")
        ));
    }

    public static class ProfileNotFoundException extends RuntimeException {
        public ProfileNotFoundException(String msg) {
            super(msg);
        }
    }
}