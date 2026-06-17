package com.example.demo.repository;

import com.example.demo.entity.SavedScheme;
import com.example.demo.entity.Scheme;
import com.example.demo.entity.User;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface SavedSchemeRepository
        extends JpaRepository<SavedScheme, Long> {

    List<SavedScheme> findByUser(User user);

    Optional<SavedScheme> findByUserAndScheme(
            User user,
            Scheme scheme
    );
}