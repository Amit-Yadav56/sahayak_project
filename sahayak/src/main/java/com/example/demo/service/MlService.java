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

import com.example.demo.entity.UserProfile;

@Slf4j
@Service
@RequiredArgsConstructor
public class MlService {

    @Value("${ml.service.url:http://localhost:8000}")
    private String mlServiceUrl;

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;

    // POST /match - Score all schemes for a user profile
    public JsonNode matchSchemes(UserProfile profile, int topN, String minStatus) {
        ObjectNode user = objectMapper.createObjectNode();
        user.put("age", profile.getAge() != null ? profile.getAge() : 0);
        user.put("gender", profile.getGender() != null ? profile.getGender() : "other");
        user.put("state", (profile.getUser() != null && profile.getUser().getState() != null) ? profile.getUser().getState() : "");
        user.put("annual_income", profile.getAnnualIncome() != null ? profile.getAnnualIncome().intValue() : 0);
        user.put("income_source", profile.getIncomeSource() != null ? profile.getIncomeSource() : "other");
        user.put("caste_category", profile.getCasteCategory() != null ? profile.getCasteCategory() : "General");
        user.put("disability", profile.getDisabilityType() != null && !profile.getDisabilityType().isBlank());
        user.put("is_widow", profile.getIsWidow() != null && profile.getIsWidow());
        user.put("education_level", profile.getEducationLevel() != null ? profile.getEducationLevel() : "none");
        user.put("has_bank_account", profile.getHasBankAccount() != null && profile.getHasBankAccount());
        user.put("has_aadhar", profile.getHasAadhar() != null && profile.getHasAadhar());
        user.put("land_ownership", profile.getLandAcres() != null ? profile.getLandAcres() : 0.0);
        user.put("has_house", profile.getHasHouse() != null && profile.getHasHouse());
        user.put("children_count", profile.getChildrenCount() != null ? profile.getChildrenCount() : 0);

        ObjectNode body = objectMapper.createObjectNode();
        body.set("user", user);
        body.put("top_n", topN);
        body.put("min_status", minStatus);

        return post("/match", body);
    }

    // POST /search - Semantic search over schemes
    public JsonNode searchSchemes(String query, String language, int topK) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("query", query);
        body.put("language", language != null ? language : "en");
        body.put("top_k", topK);
        return post("/search", body);
    }

    // POST /extract-criteria - Extract structured eligibility JSON from raw text
    public JsonNode extractCriteria(String text, String stateHint) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("text", text);
        body.put("state_hint", stateHint != null ? stateHint : "any");
        return post("/extract-criteria", body);
    }

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
