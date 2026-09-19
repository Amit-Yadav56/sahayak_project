# Sahayak — Government Welfare Scheme Eligibility Platform

A Spring Boot backend for **Sahayak**, a platform that helps citizens discover Indian government welfare schemes they're eligible for. Users register, fill out a socioeconomic profile, and the system — via an internal **Python FastAPI ML service** — matches, ranks, and semantically searches schemes for them. Admins can manage the scheme catalog, including auto-extracting eligibility rules from a scheme's webpage URL.

**From your CV:**
- Aggregated **~4,500 Indian government welfare schemes** scraped from the **myScheme API** and a **Kaggle dataset**, cleaned and normalized down to **~3,500 structured scheme records**.
- Designed a **6-table PostgreSQL schema**: users, profiles, schemes, matches, saved schemes, search logs.
- Built **12+ REST endpoints** for authentication, profile management, scheme matching, and saved schemes — secured end-to-end with JWT.
- Deliberately kept Spring Boot and ML separated: Java owns auth/persistence/business logic; Python FastAPI owns eligibility scoring. The Java layer never touches the ML models directly.
- The hard part was upstream of the API: raw government scheme text is free-form, not structured, so cleaning it into a consistent schema shaped the data model and endpoint design.

> Note: the uploaded zip contains only the `com.example.demo` Java source tree (controllers/services/entities/dto/repository/security/config) — no `pom.xml`/`build.gradle`, `application.properties`, the Python ML service source, or the scraping/cleaning pipeline. This README maps what's in the code to what's on your CV. The code shows **4 entities/tables** (User, UserProfile, Scheme, SavedScheme) and **~19 endpoints** across 6 controllers — your CV says 6 tables and 12+ endpoints, so a **"matches" table and a "search logs" table likely exist in your real DB but aren't in this zip's entity classes** (matches may just be computed on the fly by the ML service rather than persisted, and search logs may be a separate piece not included here). Flag this to yourself before the interview — see Section 9.

---

## 1. What the project does (elevator pitch)

"It's a two-service system: a **Spring Boot REST API** (Java) handles auth, user profiles, and the scheme catalog and stores everything in a relational DB via JPA. A separate **Python FastAPI ML service** does the intelligence — it scores/ranks schemes for a user's profile using an **XGBoost** model, does **semantic search** over scheme descriptions (likely using sentence-transformer embeddings), and extracts structured eligibility criteria from raw scraped text. The Spring Boot app calls the ML service over HTTP with `RestTemplate`."

---

## 2. Architecture

```
┌─────────────┐        JWT-authenticated REST         ┌──────────────────────┐
│   Client /   │ ─────────────────────────────────────▶│   Spring Boot API    │
│   Frontend   │◀───────────────────────────────────── │  (com.example.demo)  │
└─────────────┘                                         └──────────┬───────────┘
                                                                     │ HTTP (RestTemplate,
                                                                     │ forced HTTP/1.1)
                                                                     ▼
                                                         ┌──────────────────────┐
                                                         │  Python ML service    │
                                                         │  (FastAPI + Uvicorn)  │
                                                         │  /match  /search      │
                                                         │  /extract-criteria    │
                                                         └──────────────────────┘
                                                                     ▲
                                                         (likely XGBoost model +
                                                          sentence-transformer
                                                          embeddings, not in this zip)
```

**Two-service design.** Java handles CRUD, auth, and orchestration; Python handles ML/NLP. This is a common pattern because Java's ML ecosystem is weaker than Python's (scikit-learn/XGBoost/sentence-transformers), so the "smart" part is isolated behind a small HTTP contract.

---

## 3. Tech stack (inferred from imports)

| Layer | Technology |
|---|---|
| Language / Framework | Java, Spring Boot |
| Web | Spring Web (`@RestController`), `RestTemplate` for outbound HTTP |
| Security | Spring Security, stateless sessions, custom JWT filter, BCrypt password hashing |
| Persistence | Spring Data JPA / Hibernate (entities use `@Entity`, `@ManyToOne`, `@OneToOne`) — likely PostgreSQL or MySQL |
| JSON | Jackson (`ObjectMapper`, `JsonNode`, `ObjectNode`) |
| HTML scraping | Jsoup (fetches and parses scheme web pages) |
| Boilerplate reduction | Lombok (`@Data`, `@Builder`, `@RequiredArgsConstructor`, `@Getter/@Setter`) |
| Logging | SLF4J (`@Slf4j`) |
| Auth tokens | JJWT (`io.jsonwebtoken`) — HMAC-SHA signed JWTs |
| ML/NLP service | Separate Python service (FastAPI/Uvicorn implied by comments), likely XGBoost + sentence embeddings — **not included in this zip, verify separately** |

---

## 4. Package structure

```
com.example.demo
├── DemoApplication.java        — Spring Boot entry point
├── config/
│   ├── SecurityConfig.java     — security filter chain, password encoder bean
│   └── MlServiceConfig.java    — RestTemplate bean configured for the ML service
├── controller/
│   ├── AuthController          — register / login / me / logout
│   ├── ProfileController       — create / get / update user profile
│   ├── SchemeController        — list/get/search/semantic-search/ML-matched schemes, admin URL parsing
│   ├── AdminSchemeController   — admin create/update scheme (ROLE_ADMIN only)
│   ├── SavedSchemeController   — save / unsave / list saved schemes
│   └── HealthController        — GET /api/health
├── service/
│   ├── UserService              — register/login/profile business logic
│   ├── SchemeService             — scheme CRUD + delegates semantic search to ML
│   ├── SavedSchemeService        — bookmarking logic
│   ├── MlService                  — HTTP client wrapper for the Python ML service
│   └── MlWarmup                   — fires a dummy request at startup to pre-warm the ML model
├── security/
│   ├── JwtUtil                   — generate/validate/parse JWTs
│   ├── JwtFilter                 — OncePerRequestFilter, reads Bearer token, sets SecurityContext
│   └── CustomUserDetailsService  — loads Spring Security UserDetails from the DB by email
├── entity/    — User, UserProfile, Scheme, SavedScheme (JPA entities)
├── dto/       — request/response DTOs for each endpoint
└── repository/ — Spring Data JPA repositories
```

---

## 5. Data model

- **User** — id, name, email (unique), passwordHash, phone, state, district, preferredLanguage, createdAt, role (`USER`/`ADMIN`).
- **UserProfile** (1:1 with User) — age, gender, casteCategory, annualIncome, incomeSource, landAcres, hasHouse, isWidow, disabilityType, childrenCount, educationLevel, hasBankAccount, hasAadhar, updatedAt. This is exactly the feature vector sent to the ML `/match` endpoint.
- **Scheme** — name, ministry, category, subcategory, description, benefitType, benefitAmount, eligibilitySummary, eligibilityJson (TEXT — structured rules, likely produced by the ML `/extract-criteria` endpoint), documentsRequired, howToApply, applicationUrl, deadline, state, isActive, lastUpdated.
- **SavedScheme** — join entity between User and Scheme (many-to-one both ways) with savedAt + notes — this is the "bookmark" feature.

---

## 6. API surface

### Auth (`/api/auth`) — public except `/me`
- `POST /register` — creates a user with `role=USER`, BCrypt-hashes the password.
- `POST /login` — verifies password, returns a JWT (`LoginResponse`).
- `GET /me` — returns the current user from the `Authentication` principal.
- `POST /logout` — stateless JWT, so this is just a no-op/placeholder message (no server-side session to invalidate).

### Profile (`/api/profile`) — authenticated
- `POST` / `GET` / `PUT` — create, fetch, update the caller's `UserProfile`.

### Schemes (`/api/schemes`)
- `GET /` , `GET /{id}`, `GET /category/{cat}`, `GET /search?q=` — plain DB-backed queries.
- `GET /semantic-search?q=&language=&topK=` — proxies to the ML service's `/search` (embedding-based search, multi-language).
- `GET /my?topN=&minStatus=` — **the core feature**: loads the caller's profile, calls ML `/match`, returns a ranked, scored list of schemes with eligibility status (`ELIGIBLE` / `LIKELY_ELIGIBLE` / `CHECK_REQUIRED`) and per-criterion match detail.
- `POST /admin/parse-url` — admin tool: fetches a scheme's webpage with Jsoup, extracts the eligibility section (falls back to full body text, capped at 3000 chars), sends it to ML `/extract-criteria`, returns structured `eligibility_json` for the admin to review before saving.

### Admin Schemes (`/api/admin/schemes`) — `ROLE_ADMIN` only
- `POST` / `PUT /{id}` — create/update scheme records.

### Saved Schemes (`/api/saved`) — authenticated
- `GET` / `POST /{schemeId}` / `DELETE /{schemeId}` — bookmark list, save, unsave.

### Health
- `GET /api/health` — simple liveness check.

---

## 7. Security design

- **Stateless JWT auth.** No server-side sessions (`SessionCreationPolicy.STATELESS`), CSRF disabled (safe here because there's no cookie-based session to forge).
- **JwtFilter** runs once per request, reads the `Authorization: Bearer <token>` header, validates the signature/expiry with `JwtUtil`, loads the user via `CustomUserDetailsService`, and manually populates the `SecurityContextHolder`.
- **Password hashing** via `BCryptPasswordEncoder`.
- **Role-based access**: `/api/admin/**` requires `ROLE_ADMIN` (Spring Security's `hasRole` auto-prefixes `ROLE_`, and `User.role` stores the raw `"USER"`/`"ADMIN"` string).
- **Public endpoints**: only `/api/auth/register` and `/api/auth/login`; everything else needs a valid token.
- JWTs are signed HMAC-SHA (`Keys.hmacShaKeyFor`), expire after 24h (`86400000` ms), subject = user's email.

**Known rough edges worth being honest about in an interview** (shows self-awareness):
- `JwtFilter` has leftover `System.out.println` debug statements (should be `log.debug`, and removed/gated before production).
- If a JWT is invalid, the filter silently falls through to `filterChain.doFilter` rather than returning 401 immediately — the request just proceeds unauthenticated and gets rejected downstream by the authorization rule instead. Works, but isn't the most explicit way to fail.
- `UserService`/`SchemeService` throw generic `RuntimeException` for "not found" / "already exists" cases instead of custom exception types mapped to proper HTTP status codes via `@ControllerAdvice` — right now those probably surface as generic 500s instead of 404/409.

---

## 8. Integration with the ML service

`MlService` is a thin, well-documented HTTP client with three calls:

| Endpoint | Called by | Purpose |
|---|---|---|
| `POST /match` | `GET /api/schemes/my` | Send the user's full profile as JSON, get back scored/ranked/status-labeled schemes. |
| `POST /search` | `GET /api/schemes/semantic-search`, and `MlWarmup` at startup | Natural-language semantic search over scheme descriptions, multi-language. |
| `POST /extract-criteria` | `POST /api/schemes/admin/parse-url` | Turn raw scraped eligibility text into structured JSON criteria. |

Notable implementation details:
- `MlServiceConfig` deliberately uses `SimpleClientHttpRequestFactory` instead of the default request factory to **force HTTP/1.1** — because Uvicorn (the ASGI server running FastAPI) doesn't support HTTP/2 cleartext (h2c) upgrade, and the default factory can attempt that.
- `MlWarmup` implements `ApplicationRunner` and fires a dummy semantic-search call **on a background thread at startup**, so the (likely large) sentence-transformer embedding model is loaded into memory before the first real user hits it — trading a slower app startup for a faster first request. Failure here is caught and just logged as a warning, not fatal.
- Errors are wrapped in a custom unchecked `MlServiceException` distinguishing serialization failures from the ML service being unreachable/erroring.

---

## 9. Things to verify before your interview (not in this zip)

The archive only had the Java source under `com/example/demo`. Before the interview, confirm/gather:

- [ ] **Build tool & dependencies** — Maven (`pom.xml`) or Gradle? Spring Boot version, Java version.
- [ ] **`application.properties`/`.yml`** — DB URL/driver (should be PostgreSQL per your CV), `jwt.secret`, `ml.service.url`, timeouts.
- [ ] **Migrations** — Flyway/Liquibase, or `ddl-auto`?
- [ ] **The "6-table" claim** — this zip's entities only map to 4 tables (`users`, `user_profiles`, `schemes`, `saved_schemes`). Find the real `matches` and `search_logs` tables/entities (probably in a version of the code not in this zip) so you can describe their columns if asked.
- [ ] **The "12+ endpoints" claim** — this zip actually has ~19 mapped endpoints across 6 controllers (see Section 6), which is consistent with "12+." Good — but double check nothing here is dead/unused code you'd be caught out on.
- [ ] **The scraping/cleaning pipeline** — how the myScheme API was called (auth? rate limits? pagination?), how the Kaggle dataset was merged with it, what "cleaned and normalized ~4,500 → ~3,500" actually involved (dedup? dropping incomplete records? standardizing category/state names?). This is likely a separate script/notebook, not in this zip — locate it.
- [ ] **The Python ML service source** — what model is actually used for `/match` (your CV doesn't specify; earlier drafts assumed XGBoost — confirm), what embedding model powers `/search` (sentence-transformers is a guess), how "search logs" get written (does `/search` or `/semantic-search` log to the `search_logs` table?).
- [ ] **The "matches" table** — is it a persisted cache of scored results per user, or just implied by the `/match` ML call? The current `SchemeController.getMySchemes` code passes the ML response straight through without saving it anywhere — if your CV says there's a matches table, find where it's actually written.
- [ ] **Deployment** — Docker? Docker Compose linking the two services? Cloud provider? CI/CD?
- [ ] **Tests** — any unit/integration tests present in the real repo?
- [ ] **Frontend** — what consumes this API? Any UI to demo?

---

## 10. Likely interview questions & how to answer them

**"Walk me through what happens when a logged-in user hits `GET /api/schemes/my`."**
Request comes in with a Bearer token → `JwtFilter` validates it and sets the `SecurityContext` → `SchemeController.getMySchemes` looks up the `User` by the authenticated email, then the `UserProfile` for that user (404/error if profile isn't filled out yet) → builds a JSON payload of ~14 profile fields → `MlService.matchSchemes` POSTs it to the Python service's `/match` → the raw JSON response (scores, statuses, matched_criteria) is passed straight back to the client via `ResponseEntity`.

**"Why split this into two services instead of one Java monolith?"**
ML/NLP tooling (XGBoost, sentence-transformers) is far more mature in Python; keeping it separate also lets each service scale and deploy independently, and keeps the Java side focused on CRUD/auth.

**"How do you secure the API?"**
Stateless JWT bearer auth validated on every request by a custom `OncePerRequestFilter`, role-based route authorization, BCrypt for passwords, CSRF disabled because there are no cookie sessions.

**"What would you improve if you had more time?"**
Proper exception handling with `@ControllerAdvice` mapping domain exceptions to HTTP status codes (right now most failures are generic `RuntimeException` → 500), removing debug `System.out.println`s from `JwtFilter`, adding refresh tokens (current JWTs are 24h with no revocation), input validation on more DTOs (only `RegisterRequest` currently uses `@Valid`), and tests.

**"Why force HTTP/1.1 in `MlServiceConfig`?"**
Because Uvicorn doesn't support HTTP/2 cleartext (h2c) upgrade requests, which Spring's default request factory can attempt, causing failed/hanging calls to the ML service.

**"What's the ML warmup trick for?"**
Sentence-transformer models are slow to load into memory on first use. Firing a dummy request in a background thread at app startup absorbs that cold-start cost before real users arrive, without blocking Spring Boot's own startup.

**"How would you scale the ML matching if the scheme catalog grew to millions of rows?"**
Good place to talk about pre-computed embeddings + a vector index (e.g. FAISS/pgvector) instead of scoring every scheme per request, caching common profile → result sets, and batching/async calls between the two services.

**"You said you aggregated ~4,500 schemes and cleaned them down to ~3,500 — what did that cleaning actually involve, and why did ~1,000 get dropped?"**
Be ready with specifics from your real pipeline: likely duplicate schemes across the myScheme API and Kaggle dataset, schemes with missing/unparseable eligibility text, expired or inactive schemes, or inconsistent state/category naming that needed standardizing before it could fit the `Scheme` entity's fields (`category`, `subcategory`, `state`, etc.). This is your strongest talking point for "real-world messy data" — don't wing it, recall an actual example of a scheme record that was broken and how you fixed or excluded it.

**"Walk me through the 6-table schema."**
From the code: `users` (auth/identity), `user_profiles` (1:1, the ML feature vector), `schemes` (the catalog), `saved_schemes` (many-to-many join, user bookmarks). Be ready to explain what `matches` (likely: persisted per-user scored results, maybe used for caching or an activity/history view) and `search_logs` (likely: query text, user, timestamp, result count — used for analytics or to improve semantic search) store, even though they aren't in this particular code drop.

**"Why keep Java and Python cleanly separated instead of calling a model file directly from Java?"**
Java has weak first-class support for XGBoost/embedding models compared to Python; separating them means the ML side can be iterated on, retrained, or swapped independently without redeploying the API, and each service can be scaled to its own load profile (ML inference is likely more CPU/memory-hungry than the CRUD API).

**"Tell me about your internship at DeepThought — how does frontend work there connect to this backend project?"**
Different skill emphasis: at DeepThought you worked inside an existing production codebase and delivery process (sprints, client feedback, cross-team communication, performance fixes like the Redux selector caching to cut duplicate API calls). Sahayak is the reverse — you owned the backend design from scratch (schema, endpoints, security, service boundaries). Good contrast to highlight: "shipping inside someone else's system under real deadlines" vs. "designing a system's shape from zero."

---

## 11. Quick glossary for your CV/interview

- **JWT (JSON Web Token)** — signed token used here to prove identity statelessly, no server-side session.
- **XGBoost** — gradient-boosted decision tree library, used (per this project) to classify/score scheme eligibility per user.
- **Semantic search** — search by meaning (via text embeddings) rather than exact keyword match.
- **JPA/Hibernate** — Java's ORM layer mapping the `entity` classes to DB tables.
- **DTO (Data Transfer Object)** — plain classes (`dto/` package) used to shape request/response payloads separately from entities.
