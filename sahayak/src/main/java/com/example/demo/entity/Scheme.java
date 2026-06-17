package com.example.demo.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Entity
@Table(name = "schemes")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Scheme {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private String ministry;

    private String category;

    private String subcategory;

    @Column(columnDefinition = "TEXT")
    private String description;

    private String benefitType;

    private String benefitAmount;

    private String eligibilitySummary;

    @Column(columnDefinition = "TEXT")
    private String eligibilityJson;

    @Column(columnDefinition = "TEXT")
    private String documentsRequired;

    @Column(columnDefinition = "TEXT")
    private String howToApply;

    private String applicationUrl;

    private LocalDate deadline;

    private String state;

    private Boolean isActive;

    private LocalDateTime lastUpdated;
}