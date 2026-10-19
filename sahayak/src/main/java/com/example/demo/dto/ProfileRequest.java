package com.example.demo.dto;

import lombok.Data;

@Data
public class ProfileRequest {

    private Integer age;
    private String gender;
    private String casteCategory;
    private Double annualIncome;
    private String incomeSource;
    private Double landAcres;
    private Boolean hasHouse;
    private Boolean isWidow;
    private String disabilityType;
    private Integer childrenCount;
    private String educationLevel;
    private Boolean hasBankAccount;
    private Boolean hasAadhar;
    private String state;
}