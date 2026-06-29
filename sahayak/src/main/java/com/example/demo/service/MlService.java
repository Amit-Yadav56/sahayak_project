package com.example.demo.service;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.jsoup.Jsoup;

import com.example.demo.entity.UserProfile;

import java.util.Map;

/**
 * MlService
 * ==========
 * HTTP client that calls the Python FastAPI ML service.
 * All three endpoints are covered:
 *   POST /match              → matchSchemes()
 *   POST /search             → searchSchemes()
 *   POST /extract-criteria   → extractCriteria()
 *
 * Configuration (application.properties):
 *   ml.service.url=http://localhost:8000
 *   ml.service.timeout-ms=5000
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class MlService {

    @Value("${ml.service.url:http://localhost:8000}")
    private String mlServiceUrl;

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;

    // ── POST /match ──────────────────────────────────────────────────────────

    /**
     * Score all schemes for a user profile.
     * Called by GET /api/schemes/my.
     *
     * @param profile  the logged-in user's profile from the DB
     * @param topN     max results to return
     * @param minStatus  "ELIGIBLE" / "LIKELY_ELIGIBLE" / "CHECK_REQUIRED"
     * @return JSON from ML service: { total_schemes, returned, elapsed_ms, results: [...] }
     */
    public JsonNode matchSchemes(UserProfile profile, int topN, String minStatus) {
        ObjectNode user = objectMapper.createObjectNode();
        user.put("age",              profile.getAge() != null ? profile.getAge() : 0);
        user.put("gender",           profile.getGender() != null ? profile.getGender() : "other");
        user.put("state",            profile.getUser().getState() != null ?profile.getUser().getState() : "");
        user.put("annual_income",    profile.getAnnualIncome() != null ? profile.getAnnualIncome().intValue() : 0);
        user.put("income_source",    profile.getIncomeSource() != null ? profile.getIncomeSource() : "other");
        user.put("caste_category",   profile.getCasteCategory() != null ? profile.getCasteCategory() : "General");
        user.put("disability",       profile.getDisabilityType() != null && !profile.getDisabilityType().isBlank());
        user.put("is_widow",         profile.getIsWidow() != null && profile.getIsWidow());
        user.put("education_level",  profile.getEducationLevel() != null ? profile.getEducationLevel() : "none");
        user.put("has_bank_account", profile.getHasBankAccount() != null && profile.getHasBankAccount());
        user.put("has_aadhar",       profile.getHasAadhar() != null && profile.getHasAadhar());
        user.put("land_ownership",   profile.getLandAcres() != null ? profile.getLandAcres() : 0.0);
        user.put("has_house",        profile.getHasHouse() != null && profile.getHasHouse());
        user.put("children_count",   profile.getChildrenCount() != null ? profile.getChildrenCount() : 0);

        ObjectNode body = objectMapper.createObjectNode();
        body.set("user", user);
        body.put("top_n", topN);
        body.put("min_status", minStatus);

        return post("/match", body);
    }

    // ── POST /search ─────────────────────────────────────────────────────────

    /**
     * Semantic search over schemes.
     *
     * @param query    natural language query from the user
     * @param language BCP-47 language code ("en", "hi", "ta", ...)
     * @param topK     number of results
     * @return JSON: { query, model, elapsed_ms, returned, results: [...] }
     */
    public JsonNode searchSchemes(String query, String language, int topK) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("query",    query);
        body.put("language", language != null ? language : "en");
        body.put("top_k",    topK);
        return post("/search", body);
    }

    // ── POST /extract-criteria ────────────────────────────────────────────────

    /**
     * Extract structured eligibility JSON from raw text.
     * Used by POST /api/admin/schemes/parse-url — fetches page text from the URL,
     * sends it here, stores the structured result.
     *
     * @param text      raw eligibility text (caller is responsible for fetching)
     * @param stateHint scheme's state if known, or "any"
     * @return JSON: { eligibility_json: {...}, elapsed_ms, input_length }
     */
    public JsonNode extractCriteria(String text, String stateHint) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("text",       text);
        body.put("state_hint", stateHint != null ? stateHint : "any");
        return post("/extract-criteria", body);
    }

    // ── Shared HTTP helper ────────────────────────────────────────────────────

    private JsonNode post(String path, Object body) {
        String url = mlServiceUrl + path;
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        try {
            String jsonBody = objectMapper.writeValueAsString(body);
            log.info("Sending to {}: {}", url, jsonBody);

            ResponseEntity<JsonNode> response = restTemplate.exchange(
                    url,
                    HttpMethod.POST,
                    new HttpEntity<>(jsonBody, headers),
                    JsonNode.class
            );
            if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
                return response.getBody();
            }
            log.error("ML service {} returned {}", path, response.getStatusCode());
            throw new MlServiceException("ML service returned " + response.getStatusCode());
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize request body for {}: {}", path, e.getMessage());
            throw new MlServiceException("Failed to serialize request: " + e.getMessage(), e);
        } catch (RestClientException e) {
            log.error("ML service {} unreachable: {}", path, e.getMessage());
            throw new MlServiceException("ML service unavailable: " + e.getMessage(), e);
        }
    }
    public static class MlServiceException extends RuntimeException {
        public MlServiceException(String msg) { super(msg); }
        public MlServiceException(String msg, Throwable cause) { super(msg, cause); }
    }
}
