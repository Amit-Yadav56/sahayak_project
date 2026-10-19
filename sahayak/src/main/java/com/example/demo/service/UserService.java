package com.example.demo.service;

import com.example.demo.dto.*;
import com.example.demo.entity.User;
import com.example.demo.entity.UserProfile;
import com.example.demo.repository.UserProfileRepository;
import com.example.demo.repository.UserRepository;
import com.example.demo.security.JwtUtil;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
public class UserService {

    private final JwtUtil jwtUtil;
    private final UserRepository userRepository;
    private final UserProfileRepository userProfileRepository;
    private final PasswordEncoder passwordEncoder;

    // Register user
    public String register(RegisterRequest request) {
        if (userRepository.findByEmail(request.getEmail()).isPresent()) {
            throw new RuntimeException("Email already exists");
        }

        User user = User.builder()
            .name(request.getName())
            .email(request.getEmail())
            .passwordHash(passwordEncoder.encode(request.getPassword()))
            .state(request.getState())
            .role("USER")
            .createdAt(LocalDateTime.now())
            .build();

        userRepository.save(user);
        return "User Registered Successfully";
    }

    // Login user
    public LoginResponse login(LoginRequest request) {
        User user = userRepository.findByEmail(request.getEmail()).orElseThrow(() -> new RuntimeException("User not found"));

        boolean matches = passwordEncoder.matches(request.getPassword(), user.getPasswordHash());
        if (!matches) {
            throw new RuntimeException("Invalid password");
        }

        String token = jwtUtil.generateToken(user.getEmail());
        return new LoginResponse(token, user.getName(), user.getEmail());
    }

    // Get current user details
    public UserResponse getCurrentUser(String email) {
        User user = userRepository.findByEmail(email).orElseThrow(() -> new RuntimeException("User not found"));

        return new UserResponse(
            user.getId(),
            user.getName(),
            user.getEmail(),
            user.getRole()
        );
    }

    // Create profile (upsert if exists)
    public String createProfile(String email, ProfileRequest request) {
        User user = userRepository.findByEmail(email).orElseThrow(() -> new RuntimeException("User not found"));

        if (userProfileRepository.findByUser(user).isPresent()) {
            return updateProfile(email, request);
        }

        UserProfile profile = UserProfile.builder()
            .age(request.getAge())
            .gender(request.getGender())
            .casteCategory(request.getCasteCategory())
            .annualIncome(request.getAnnualIncome())
            .incomeSource(request.getIncomeSource())
            .landAcres(request.getLandAcres())
            .hasHouse(request.getHasHouse())
            .isWidow(request.getIsWidow())
            .disabilityType(request.getDisabilityType())
            .childrenCount(request.getChildrenCount())
            .educationLevel(request.getEducationLevel())
            .hasBankAccount(request.getHasBankAccount())
            .hasAadhar(request.getHasAadhar())
            .updatedAt(LocalDateTime.now())
            .user(user)
            .build();

        if (request.getState() != null && !request.getState().isBlank()) {
            user.setState(request.getState());
            userRepository.save(user);
        }

        userProfileRepository.save(profile);
        return "Profile created successfully";
    }

    // Get profile details
    public UserProfile getProfile(String email) {
        User user = userRepository.findByEmail(email).orElseThrow(() -> new RuntimeException("User not found"));

        return userProfileRepository.findByUser(user).orElseThrow(() -> new ProfileNotFoundException("Profile not found for user: " + email));
    }

    public static class ProfileNotFoundException extends RuntimeException {
        public ProfileNotFoundException(String msg) { super(msg); }
    }

    // Update profile details (creates if not exists)
    public String updateProfile(String email, ProfileRequest request) {
        User user = userRepository.findByEmail(email).orElseThrow(() -> new RuntimeException("User not found"));

        java.util.Optional<UserProfile> existing = userProfileRepository.findByUser(user);
        if (existing.isEmpty()) {
            return createProfile(email, request);
        }

        UserProfile profile = existing.get();

        if (request.getAge() != null) profile.setAge(request.getAge());
        if (request.getGender() != null) profile.setGender(request.getGender());
        if (request.getCasteCategory() != null) profile.setCasteCategory(request.getCasteCategory());
        if (request.getAnnualIncome() != null) profile.setAnnualIncome(request.getAnnualIncome());
        if (request.getIncomeSource() != null) profile.setIncomeSource(request.getIncomeSource());
        if (request.getLandAcres() != null) profile.setLandAcres(request.getLandAcres());
        if (request.getHasHouse() != null) profile.setHasHouse(request.getHasHouse());
        if (request.getIsWidow() != null) profile.setIsWidow(request.getIsWidow());
        if (request.getDisabilityType() != null) profile.setDisabilityType(request.getDisabilityType());
        if (request.getChildrenCount() != null) profile.setChildrenCount(request.getChildrenCount());
        if (request.getEducationLevel() != null) profile.setEducationLevel(request.getEducationLevel());
        if (request.getHasBankAccount() != null) profile.setHasBankAccount(request.getHasBankAccount());
        if (request.getHasAadhar() != null) profile.setHasAadhar(request.getHasAadhar());

        if (request.getState() != null && !request.getState().isBlank()) {
            user.setState(request.getState());
            userRepository.save(user);
        }

        profile.setUpdatedAt(LocalDateTime.now());
        userProfileRepository.save(profile);

        return "Profile updated successfully";
    }
}