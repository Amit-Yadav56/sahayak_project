package com.example.demo.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

/**
 * MlServiceConfig
 * ================
 * Configures the RestTemplate used by MlService to call the Python FastAPI.
 * Uses SimpleClientHttpRequestFactory to force HTTP/1.1 (no h2c upgrade),
 * which Uvicorn requires.
 *
 * application.properties:
 *   ml.service.url=http://localhost:8000
 *   ml.service.connect-timeout-ms=3000
 *   ml.service.read-timeout-ms=10000
 */
@Configuration
public class MlServiceConfig {

    @Value("${ml.service.connect-timeout-ms:3000}")
    private int connectTimeoutMs;

    @Value("${ml.service.read-timeout-ms:10000}")
    private int readTimeoutMs;

    @Bean
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connectTimeoutMs);
        factory.setReadTimeout(readTimeoutMs);

        return builder
                .requestFactory(() -> factory)
                .build();
    }
}