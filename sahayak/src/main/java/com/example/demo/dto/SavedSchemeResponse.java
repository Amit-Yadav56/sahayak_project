package com.example.demo.dto;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@AllArgsConstructor
public class SavedSchemeResponse {

    private Long savedId;
    private Long schemeId;
    private String schemeName;
    private String category;
    private String benefitAmount;
    private LocalDateTime savedAt;
}