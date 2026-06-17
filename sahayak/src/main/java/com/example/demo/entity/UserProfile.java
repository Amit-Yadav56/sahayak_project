package com.example.demo.entity;
import jakarta.persistence.*;
import java.time.LocalDateTime;
import lombok.*;
@Entity
@Table(name="user_profiles")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UserProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

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

    private LocalDateTime updatedAt;

    @OneToOne
    @JoinColumn(name="user_id")
    private User user;
}