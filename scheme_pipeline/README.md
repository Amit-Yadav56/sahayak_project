# Scheme Pipeline & ML Service (Python)

This service scrapes Indian government schemes, extracts eligibility conditions, and runs the FastAPI service that calculates eligibility scores for the Spring Boot backend.

## Requirements

- Python 3.10+
- PostgreSQL

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Setup `.env` file with your database details:

```bash
cp .env.example .env
```

Edit `.env` with your Postgres password and database name.

## Running the ML API

Start the FastAPI server:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

The service runs at http://localhost:8000.
Interactive docs are at http://localhost:8000/docs.

## Endpoints used by Spring Boot

- `POST /match`: Takes user profile and returns ranked schemes with eligibility scores.
- `POST /search`: Natural language query search over scheme descriptions.
- `POST /extract-criteria`: Parses raw web text from a scheme URL into structured JSON.

## Running the data pipeline

To run all steps (scraping, normalizing, database loading):

```bash
python pipeline.py
```

To test with only 10 schemes:

```bash
python pipeline.py --max 10 --reset-db
```