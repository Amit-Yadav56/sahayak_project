# Sahayak Backend (Spring Boot)

This is the Java backend for Sahayak. It manages users, authentication, citizen profiles, and scheme data, and talks to the Python ML service over HTTP.

## Requirements

- Java 17 or newer
- PostgreSQL running on localhost:5432
- Maven (or use the included `./mvnw` / `mvnw.cmd`)

## Database setup

Create a PostgreSQL database named `sahayak`:

```sql
CREATE DATABASE sahayak;
```

Check `src/main/resources/application.properties` and change your PostgreSQL username and password if they are different:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/sahayak
spring.datasource.username=postgres
spring.datasource.password=your_password
```

## Running the backend

Using the Maven wrapper:

```bash
# On Linux/macOS
./mvnw spring-boot:run

# On Windows
mvnw.cmd spring-boot:run
```

The server runs on port 8080.

## Main Endpoints

Auth:
- POST `/api/auth/register` - Create an account
- POST `/api/auth/login` - Get a JWT token
- GET `/api/auth/me` - Get current user info

Profile:
- POST `/api/profile` - Create citizen profile
- GET `/api/profile` - Read user profile
- PUT `/api/profile` - Update profile fields

Schemes:
- GET `/api/schemes` - List all schemes
- GET `/api/schemes/{id}` - Scheme by ID
- GET `/api/schemes/category/{cat}` - Filter by category
- GET `/api/schemes/search?q=...` - Keyword search
- GET `/api/schemes/my` - Returns schemes matched by the ML service for the logged-in user
- GET `/api/schemes/semantic-search?q=...` - Semantic search using sentence embeddings

Saved:
- GET `/api/saved` - View saved schemes
- POST `/api/saved/{schemeId}` - Bookmark a scheme
- DELETE `/api/saved/{schemeId}` - Remove bookmark
