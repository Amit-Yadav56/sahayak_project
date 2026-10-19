package com.example.demo.service;

import com.example.demo.dto.SchemeRequest;
import com.example.demo.entity.Scheme;
import com.example.demo.repository.SchemeRepository;
import com.fasterxml.jackson.databind.JsonNode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class SchemeService {

    private final SchemeRepository schemeRepository;
    private final MlService mlService;

    public List<Scheme> getAllSchemes() {
        return schemeRepository.findAll();
    }

    public Scheme getSchemeById(Long id) {
        return schemeRepository.findById(id).orElseThrow(() -> new RuntimeException("Scheme not found"));
    }

    public List<Scheme> getSchemesByCategory(String category) {
        return schemeRepository.findByCategory(category);
    }

    public List<Scheme> searchSchemes(String query) {
        return schemeRepository.findByNameContainingIgnoreCase(query);
    }

    public JsonNode semanticSearch(String query, String language, int topK) {
        log.info("Semantic search: query='{}' language={} topK={}", query, language, topK);
        return mlService.searchSchemes(query, language, topK);
    }

    public Scheme createScheme(SchemeRequest request) {
        Scheme scheme = Scheme.builder()
            .name(request.getName())
            .ministry(request.getMinistry())
            .category(request.getCategory())
            .subcategory(request.getSubcategory())
            .description(request.getDescription())
            .benefitType(request.getBenefitType())
            .benefitAmount(request.getBenefitAmount())
            .eligibilitySummary(request.getEligibilitySummary())
            .eligibilityJson(request.getEligibilityJson())
            .documentsRequired(request.getDocumentsRequired())
            .howToApply(request.getHowToApply())
            .applicationUrl(request.getApplicationUrl())
            .deadline(request.getDeadline())
            .state(request.getState())
            .isActive(request.getIsActive())
            .lastUpdated(LocalDateTime.now())
            .build();

        return schemeRepository.save(scheme);
    }

    public Scheme updateScheme(Long id, SchemeRequest request) {
        Scheme scheme = schemeRepository.findById(id).orElseThrow(() -> new RuntimeException("Scheme not found"));

        if (request.getName() != null) scheme.setName(request.getName());
        if (request.getMinistry() != null) scheme.setMinistry(request.getMinistry());
        if (request.getCategory() != null) scheme.setCategory(request.getCategory());
        if (request.getSubcategory() != null) scheme.setSubcategory(request.getSubcategory());
        if (request.getDescription() != null) scheme.setDescription(request.getDescription());
        if (request.getBenefitType() != null) scheme.setBenefitType(request.getBenefitType());
        if (request.getBenefitAmount() != null) scheme.setBenefitAmount(request.getBenefitAmount());
        if (request.getEligibilitySummary() != null) scheme.setEligibilitySummary(request.getEligibilitySummary());
        if (request.getEligibilityJson() != null) scheme.setEligibilityJson(request.getEligibilityJson());
        if (request.getDocumentsRequired() != null) scheme.setDocumentsRequired(request.getDocumentsRequired());
        if (request.getHowToApply() != null) scheme.setHowToApply(request.getHowToApply());
        if (request.getApplicationUrl() != null) scheme.setApplicationUrl(request.getApplicationUrl());
        if (request.getDeadline() != null) scheme.setDeadline(request.getDeadline());
        if (request.getState() != null) scheme.setState(request.getState());
        if (request.getIsActive() != null) scheme.setIsActive(request.getIsActive());

        scheme.setLastUpdated(LocalDateTime.now());
        return schemeRepository.save(scheme);
    }
}