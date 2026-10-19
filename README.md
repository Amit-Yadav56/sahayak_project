# Sahayak

Sahayak is a platform to help citizens discover Indian welfare schemes they qualify for.


# 1 Spring Boot (Java)
mvn -q spring-boot:run
# 2 FastAPI ML service (Python)
python -m uvicorn scheme_pipeline.api:app --reload --port 8000
# 3 Front‑end (React/Vite)
npm run dev
## Project Structure

- `frontend/`: React showcase app with scheme search and eligibility calculator.
- `sahayak/`: Java Spring Boot backend for auth, profiles, and scheme records.
- `scheme_pipeline/`: Python FastAPI service for eligibility matching and scrapers.

## How to run everything

1. Start PostgreSQL and create database `sahayak`:
```sql
CREATE DATABASE sahayak;
```

2. Start the Python ML service (port 8000):
```bash
cd scheme_pipeline
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

3. Start the Spring Boot backend (port 8080):
```bash
cd sahayak
./mvnw spring-boot:run
# on Windows: mvnw.cmd spring-boot:run
```

4. Start the frontend:
```bash
cd frontend
python -m http.server 3000
```
Open http://localhost:3000 in your browser.
