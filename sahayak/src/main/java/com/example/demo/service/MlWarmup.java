package com.example.demo.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * MlWarmup
 * =========
 * Fires a dummy semantic search query at Spring Boot startup so the
 * Python ML service loads the sentence-transformer model into memory
 * before the first real user request arrives.
 *
 * Without this, the first user to call /api/schemes/semantic-search
 * waits ~5 seconds while the model downloads/loads. With this warmup,
 * that delay happens at server startup instead — invisible to users.
 *
 * If the Python ML service isn't running yet when Spring Boot starts,
 * the warning is logged and ignored — the warmup will happen naturally
 * on the first real request instead.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class MlWarmup implements ApplicationRunner {

    private final MlService mlService;

    @Override
    public void run(ApplicationArguments args) {
        new Thread(() -> {
            try {
                log.info("Warming up ML semantic search model...");
                mlService.searchSchemes("government welfare schemes", "en", 1);
                log.info("ML semantic search warmup complete.");
            } catch (Exception e) {
                log.warn("ML warmup failed — ML service may not be running yet. " +
                         "First semantic search request will be slow. Error: {}", e.getMessage());
            }
        }, "ml-warmup").start();
    }
}
