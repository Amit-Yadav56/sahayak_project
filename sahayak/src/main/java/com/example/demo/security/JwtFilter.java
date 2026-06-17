package com.example.demo.security;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
@Component
@RequiredArgsConstructor
public class JwtFilter
        extends OncePerRequestFilter {

    private final JwtUtil jwtUtil;
    private final CustomUserDetailsService userDetailsService;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {
        System.out.println("JWT FILTER HIT");
        String authHeader =
                request.getHeader("Authorization");
        System.out.println(
                request.getHeader("Authorization")
        );
        if(authHeader == null ||
                !authHeader.startsWith("Bearer ")){

            filterChain.doFilter(request,response);
            return;
        }

        String token =
                authHeader.substring(7);

        if(!jwtUtil.isTokenValid(token)){
            filterChain.doFilter(request,response);
            return;
        }

        String email =
                jwtUtil.extractEmail(token);
        System.out.println(email);

        if(email != null &&
                SecurityContextHolder.getContext()
                        .getAuthentication() == null){

            UserDetails userDetails =
                    userDetailsService
                            .loadUserByUsername(email);

            UsernamePasswordAuthenticationToken authToken =
                    new UsernamePasswordAuthenticationToken(
                            userDetails,
                            null,
                            userDetails.getAuthorities()
                    );

            authToken.setDetails(
                    new WebAuthenticationDetailsSource()
                            .buildDetails(request)
            );

            SecurityContextHolder
                    .getContext()
                    .setAuthentication(authToken);
            System.out.println(
                    SecurityContextHolder
                            .getContext()
                            .getAuthentication()
                            .getAuthorities()
            );
        }
        filterChain.doFilter(request,response);
    }
}
