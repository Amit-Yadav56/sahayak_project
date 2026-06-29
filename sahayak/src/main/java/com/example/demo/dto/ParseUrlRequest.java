package com.example.demo.dto;

import lombok.Data;

@Data
public class ParseUrlRequest {
    private String url;
    private String stateHint;
}
