# Scheme Pipeline

Scrapes Indian government schemes from myscheme.gov.in, data.gov.in, and Kaggle,
normalizes eligibility data into a structured JSON format, and loads everything
into PostgreSQL.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

If you are installing on Python 3.14, make sure pip is pulling a recent pandas
release. Older pandas pins can force a NumPy source build on Windows when no
compatible wheel is available.

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env and fill in your values:
#   DB_HOST, DB_NAME, DB_USER, DB_PASSWORD
#   DATA_GOV_API_KEY   (from data.gov.in)
#   KAGGLE_USERNAME + KAGGLE_KEY  (from kaggle.com/settings → API)
```

### 3. Create PostgreSQL database

```bash
psql -U postgres -c "CREATE DATABASE schemes_db;"
```

---

## Running the pipeline

### Option A — Full pipeline (all steps)

```bash
# Test with 10 schemes first
python pipeline.py --max 10 --reset-db

# Full run
python pipeline.py
```

### Option B — One step at a time

```bash
# Step 1: Scrape all sources
python -m scrapers.myscheme       # → data/raw/myscheme_raw.json
python -m scrapers.datagovin      # → data/raw/datagovin_*.json
python -m scrapers.kaggle_dl      # → data/raw/kaggle/*/

# Step 2: Parse and normalize
python -m parsers.normalize       # → data/processed/schemes_normalized.json

# Step 3: Load into PostgreSQL
python -m db.loader               # upserts all rows
python -m db.loader --reset       # drops tables first (dev only)
```

---

## Project structure

```
scheme_pipeline/
├── .env.example          ← copy to .env and fill in credentials
├── requirements.txt
├── pipeline.py           ← master runner (run this)
│
├── scrapers/
│   ├── myscheme.py       ← scrapes myscheme.gov.in via JSON API
│   ├── datagovin.py      ← downloads from data.gov.in REST API
│   └── kaggle_dl.py      ← downloads CSVs via Kaggle Python API
│
├── parsers/
│   └── normalize.py      ← maps all sources to unified schema + builds eligibility_json
│
├── db/
│   ├── schema.sql         ← table DDL + indexes (auto-applied by loader.py)
│   └── loader.py          ← upserts data/processed/schemes_normalized.json → PostgreSQL
│
└── data/
    ├── raw/               ← raw scraped JSON and CSV files
    └── processed/         ← normalized JSON ready for DB
```

---

## eligibility_json schema

Every scheme row stores a structured `eligibility_json` JSONB column:

```json
{
  "age":           { "min": 18, "max": 60 },
  "gender":        "female",
  "income_limit":  { "annual_inr": 250000, "bpl_only": false },
  "caste":         ["SC", "ST"],
  "state":         "Tamil Nadu",
  "occupation":    ["farmer", "student"],
  "disability":    false,
  "residence":     "rural"
}
```

### Example queries

```sql
-- Schemes for women in Tamil Nadu
SELECT name, ministry
FROM schemes
WHERE eligibility_json @> '{"gender": "female", "state": "Tamil Nadu"}';

-- Schemes for SC/ST with income limit
SELECT name, eligibility_json -> 'income_limit'
FROM schemes
WHERE eligibility_json -> 'caste' ? 'SC'
  AND (eligibility_json -> 'income_limit' ->> 'annual_inr')::int > 0;

-- Schemes with disability support
SELECT name FROM schemes
WHERE eligibility_json @> '{"disability": true}';
```

If you run these queries in `psql` on Windows and see a `WIN1252` encoding
error on `₹` or other UTF-8 characters, switch the session encoding first:

```sql
\encoding UTF8
-- or
SET client_encoding = 'UTF8';
```

---

## Calibrating field names

After scraping, run this to see the exact keys the APIs return:

```python
import json
data = json.load(open("data/raw/myscheme_raw.json"))
print(list(data[0].keys()))  # see available fields
```

Then update the field mappings in `parsers/normalize.py` accordingly.
