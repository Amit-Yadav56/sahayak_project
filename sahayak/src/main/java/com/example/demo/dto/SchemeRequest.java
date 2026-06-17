package com.example.demo.dto;

import lombok.Data;

import java.time.LocalDate;

@Data
public class SchemeRequest {

    private String name;

    private String ministry;

    private String category;

    private String subcategory;

    private String description;

    private String benefitType;

    private String benefitAmount;

    private String eligibilitySummary;

    private String eligibilityJson;

    private String documentsRequired;

    private String howToApply;

    private String applicationUrl;

    private LocalDate deadline;

    private String state;

    private Boolean isActive;
}