package com.example.demo.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

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
                log.warn("ML warmup skipped (service might not be running yet): {}", e.getMessage());
            }
        }, "ml-warmup").start();
    }
}
