# Sahayak Setup & Deployment

**Local Setup**

1. Database
Make sure PostgreSQL is running locally and create the database:
```sql
CREATE DATABASE sahayak;
```

2. Python ML Service (`scheme_pipeline`)
```bash
cd scheme_pipeline
python -m venv .venv
.\.venv\Scripts\activate   # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn api.main:app --reload --port 8000
```

3. Java Backend (`sahayak`)
```bash
cd sahayak
.\mvnw.cmd spring-boot:run   # Mac/Linux: ./mvnw spring-boot:run
```

4. Frontend (`frontend`)
```bash
cd frontend
npm install
npm run dev
```

---

**Deployment**

1. Database (Render Postgres)
- Create a PostgreSQL database on Render.
- Format the JDBC connection URL for Spring Boot:
  `jdbc:postgresql://<host>:5432/<dbname>?sslmode=require`

2. Backend on Render
Create a Web Service linked to the repo:
- Root Directory: `sahayak`
- Build Command: `./mvnw clean package -DskipTests`
- Start Command: `java -jar target/demo-0.0.1-SNAPSHOT.jar`
- Environment Variables:
  - `SPRING_DATASOURCE_URL`: `jdbc:postgresql://<host>:5432/<dbname>?sslmode=require`
  - `SPRING_DATASOURCE_USERNAME`: `<db_user>`
  - `SPRING_DATASOURCE_PASSWORD`: `<db_password>`
  - `PORT`: `8080`
  - `JWT_SECRET`: `<secret>`
  - `ML_SERVICE_URL`: `<python_ml_url>`

*(Optional Dockerfile in `sahayak/Dockerfile` if preferred)*:
```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn clean package -DskipTests

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

3. Python ML on Render (Optional)
- Root Directory: `scheme_pipeline`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- Environment Variables: copy from `scheme_pipeline/.env`
*(Free tier limit is 512MB RAM — use `all-MiniLM-L6-v2` instead of `LaBSE`)*

4. Frontend on Vercel
- Import repo in Vercel.
- Set Root Directory to `frontend`.
- Framework preset: `Vite`.
- Build Command: `npm run build`, Output Directory: `dist`.
- Environment Variable: `VITE_API_BASE_URL` = `https://<backend>.onrender.com`

5. CORS Setup
If the browser blocks frontend requests to the backend, add CORS in `sahayak/src/main/java/com/example/demo/config/SecurityConfig.java`:

```java
@Bean
public CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOriginPatterns(List.of("http://localhost:*", "https://*.vercel.app"));
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("*"));
    config.setAllowCredentials(true);
    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
}
```
And add `.cors(cors -> cors.configurationSource(corsConfigurationSource()))` inside `securityFilterChain`.
