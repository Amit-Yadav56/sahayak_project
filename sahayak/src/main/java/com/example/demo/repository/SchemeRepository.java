package com.example.demo.repository;

import com.example.demo.entity.Scheme;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface SchemeRepository
        extends JpaRepository<Scheme, Long> {

    List<Scheme> findByCategory(String category);

    List<Scheme> findByState(String state);

    List<Scheme> findByIsActive(Boolean isActive);

    List<Scheme> findByCategoryAndState(
            String category,
            String state
    );

    List<Scheme> findByNameContainingIgnoreCase(String name);
}