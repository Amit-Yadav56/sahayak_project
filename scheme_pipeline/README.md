# Scheme Pipeline

Scrapes Indian government schemes from myscheme.gov.in, data.gov.in, and Kaggle,
normalizes eligibility data into a structured JSON format using a rule-based +
trainable-NER extractor, loads everything into PostgreSQL, and serves a FastAPI
that matches user profiles to schemes using XGBoost.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

If you are installing on Python 3.14, make sure pip is pulling a recent pandas
release. Older pandas pins can force a NumPy source build on Windows when no
compatible wheel is available.

`ml/ner_extractor` and `ml/eligibility_matcher` additionally need `spacy`,
`xgboost`, and `scikit-learn` (all in `requirements.txt`). No pretrained model
downloads are required — both ML models are trained from scratch on this
project's own data.

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
python -m scrapers.kaggle_dl      # → data/raw/kaggle/*/

# Step 2: Parse and normalize
python -m parsers.normalize --max 10
python -m parsers.normalize       # → data/processed/schemes_normalized.json

# Step 3: Load into PostgreSQL
python -m db.loader               # upserts all rows
python -m db.loader --reset       # drops tables first (dev only)

# Step 4: Run the API
uvicorn api.main:app --reload --port 8000
```

---

## Project structure

```
scheme_pipeline/
├── .env.example
├── requirements.txt
├── pipeline.py                    ← master runner
│
├── scrapers/
│   ├── myscheme.py                ← scrapes myscheme.gov.in via JSON API
│   ├── datagovin.py               ← downloads from data.gov.in REST API
│   └── kaggle_dl.py               ← downloads CSVs via Kaggle Python API
│
├── parsers/
│   ├── normalize.py               ← maps all sources → unified schema + eligibility_json
│   └── canonicalize.py            ← collapses duplicate strings (Degree/degree, class 10/10th standard)
│
├── ml/
│   ├── ner_extractor/
│   │   ├── extractor.py           ← MODEL 2: rule-based spaCy Matcher + regex extractor
│   │   └── __init__.py
│   │
│   └── eligibility_matcher/
│       ├── features.py            ← MODEL 1: feature encoder (user + scheme → vector)
│       ├── synthesize.py          ← synthetic training data generator
│       ├── train.py               ← XGBoost trainer + evaluator
│       ├── score.py               ← inference: user profile → ranked scheme list
│       ├── model.json             ← trained XGBoost model (generated)
│       └── __init__.py
│
├── api/
│   ├── main.py                    ← FastAPI app (2 endpoints)
│   └── __init__.py
│
├── db/
│   ├── schema.sql                 ← table DDL + indexes
│   └── loader.py                  ← upserts schemes_normalized.json → PostgreSQL
│
├── data/
│   ├── raw/                       ← raw scraped JSON and CSV files
│   ├── processed/                 ← schemes_normalized.json (ready for DB)
│   ├── synthetic_user_profiles.csv ← 500 synthetic user profiles (for reference/testing)
│   ├── train.spacy                ← NER training split (generated)
│   ├── dev.spacy                  ← NER held-out eval split (generated)
│   ├── manual_labels.json         ← human-reviewed NER labels (built by label_tool.py)
│   └── manual_labels.spacy        ← exported spaCy format of manual labels (generated)
│
├── trained_model/                 ← trained spaCy NER pipeline (generated)
│
├── audit_normalized.py            ← coverage stats + red-flag detection at full scale
├── generate_training_data.py      ← extractor spans → spaCy train/dev .spacy files
├── train_ner.py                   ← trains + evaluates the NER model
└── label_tool.py                  ← interactive CLI for manually labeling 50 paragraphs
```

---

## API

Start the server from your repo root:

```bash
uvicorn api.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the interactive Swagger UI — test both
endpoints directly in the browser without writing any curl commands.

### `POST /api/match` — Match schemes to a user profile

Takes a user profile, scores all ~4789 schemes using the XGBoost eligibility
model, and returns the top matches ranked by confidence score. Typical
response time: ~100ms for all schemes.

**Request body:**
```json
{
  "age": 28,
  "gender": "female",
  "state": "Tamil Nadu",
  "annual_income": 80000,
  "income_source": "farmer",
  "caste_category": "SC",
  "disability": false,
  "is_widow": false,
  "education_level": "class 10",
  "has_bank_account": true,
  "has_aadhar": true
}
```

**Optional query params:**
- `top_n=20` — number of results (max 200)
- `min_status=LIKELY_ELIGIBLE` — filter threshold

**Status values:**
| Status | Score | Meaning |
|---|---|---|
| `ELIGIBLE` | ≥ 0.80 | All known criteria satisfied |
| `LIKELY_ELIGIBLE` | ≥ 0.55 | Most criteria satisfied |
| `CHECK_REQUIRED` | ≥ 0.30 | Partial match — verify manually |
| `NOT_ELIGIBLE` | < 0.30 | Hard criterion violated |

**Field values:**
- `income_source`: `farmer` / `labourer` / `salaried` / `self_employed` / `unemployed` / `other`
- `caste_category`: `General` / `OBC` / `SC` / `ST` / `EWS`
- `education_level`: `none` / `class 5` / `class 8` / `class 10` / `class 12` / `diploma` / `graduate` / `postgraduate` / `phd`

---

### `GET /api/schemes` — Browse and filter schemes

Direct structured filter — no ML scoring. Useful for building filter UIs or
exploring what's in the database.

**Query params (all optional):**
- `state=Tamil Nadu`
- `gender=female`
- `category=Health`
- `caste=SC`
- `disability=true`
- `min_age=28` — schemes whose age range includes this age
- `max_income=80000` — schemes whose income limit is at least this value
- `page=1`, `per_page=20`

**Example:**
```bash
curl "http://localhost:8000/api/schemes?state=Tamil+Nadu&gender=female&caste=SC"
```

---

## ML Model 1 — Eligibility Matcher (XGBoost)

`ml/eligibility_matcher/` scores a user profile against every scheme and
returns a ranked list with confidence scores.

For each (user, scheme) pair, `features.py` builds a 33-feature vector of
direct match signals (age in range? income below cap? caste in list?) plus
raw user and scheme properties. XGBoost predicts a 0–1 score from this vector.

**Why XGBoost over simple filters:**
- Handles null eligibility fields — 83% of schemes have no age constraint,
  84% have no income constraint. A pure filter skips these; the model learns
  their typical weight from non-null examples.
- Gives smooth partial-match scores — a scheme for SC women scores 0.6 for
  an OBC woman rather than hard-zero.
- Ranks among technically-eligible schemes so the most relevant appear first.

**Retrain when your data changes:**
```bash
python -m ml.eligibility_matcher.train
# Generates 191k synthetic (user, scheme) pairs, trains XGBoost,
# evaluates on 15% held-out test set, saves eligibility_model.pkl
# (~15 seconds total)
```

**Use directly in code:**
```python
from ml.eligibility_matcher.score import EligibilityMatcher

matcher = EligibilityMatcher()   # load once at startup
results = matcher.score_user({
    "age": 28, "gender": "female", "state": "Tamil Nadu",
    "annual_income": 80000, "income_source": "farmer",
    "caste_category": "SC", "disability": False, "is_widow": False,
    "education_level": "class 10",
    "has_bank_account": True, "has_aadhar": True,
}, top_n=20)
```

**Honest caveat:** trained on synthetic data derived from the eligibility_json
rules. It handles partial matches and null fields better than rules, but the
underlying "ground truth" is still the extracted rules. Becomes meaningfully
better once real user interaction data (clicks, applications, outcomes) is
available for retraining.

---

## ML Model 2 — Eligibility Criteria Extractor (spaCy)

`ml/ner_extractor/extractor.py` turns raw eligibility text into structured
`eligibility_json`. Called automatically by `parsers/normalize.py`.

Two extraction passes:

- **AGE / GENDER / CATEGORY / OCCUPATION / EDUCATION / REQUIREMENT** — spaCy
  Matcher token patterns with context guards rejecting false positives
  (e.g. "2 to 3 years of experience" isn't an age range; numbers outside
  0–100 are rejected outright).
- **INCOME / BPL** — clause-scoped regex pass. Handles `₹48,000/-` formatting,
  `lakh`/`crore`/`LPA` multipliers, decimal amounts (`₹2.50 Lakh`), polarity
  (`"greater than X"` is a floor not a ceiling), and skips `"Income Tax Act"`
  boilerplate.

### Known limitations

- **Monthly vs. annual income** — some text only gives a monthly figure.
  The extractor reports the number as written rather than guessing ×12.
- **Two-age-bracket schemes** — a handful of schemes cover two disjoint groups
  (e.g. children under 14 AND elderly over 60). `min_age`/`max_age` can't
  represent this — schema gap, not an extraction bug.

### Auditing at scale

```bash
python audit_normalized.py
```

Run after any change to `extractor.py` or `normalize.py`. Several real bugs
were only visible at full 4789-record volume.

### Training the NER model

```bash
python generate_training_data.py   # → data/train.spacy + data/dev.spacy
python train_ner.py                # → trained_model/
```

Dev set results (336 held-out records):

| Label | P | R | F1 |
|---|---|---|---|
| AGE | 0.857 | 0.894 | 0.875 |
| CATEGORY | 1.000 | 1.000 | 1.000 |
| EDUCATION | 0.993 | 1.000 | 0.997 |
| GENDER | 0.891 | 0.990 | 0.938 |
| INCOME | 0.809 | 0.950 | 0.874 |
| OCCUPATION | 0.996 | 0.996 | 0.996 |
| REQUIREMENT | 1.000 | 1.000 | 1.000 |
| **Overall** | **0.953** | **0.983** | **0.968** |

**Caveat:** dev labels come from the same rule-based extractor the model trains
on. High F1 means the model generalizes past exact rule wording — not that
it has been validated against human ground truth.

### Manual labeling (improves the model)

```bash
python label_tool.py            # label 50 records (~3 hours)
python label_tool.py --export   # → data/manual_labels.spacy
```

Pre-fills every record with the extractor's spans — you're correcting mistakes,
not labeling from scratch. Most records need only a keypress to accept.

**Controls:**
```
Enter / y              → accept all pre-labeled entities
d N                    → delete entity N
r N LABEL              → relabel entity N  (e.g.  r 1 INCOME)
a START:END LABEL      → add a new entity by character offset
s                      → skip this record
q                      → quit and save progress
```

Progress auto-saves after every accepted record so you can stop and resume
across sessions.

**Do not add a STATE label** — state is already captured more reliably from
the structured metadata field. Stick to the six existing labels:
`AGE`, `INCOME`, `GENDER`, `CATEGORY`, `OCCUPATION`, `EDUCATION`, `REQUIREMENT`.

---

## eligibility_json schema

```json
{
  "age":           { "min": 18, "max": 60 },
  "gender":        "female",
  "income_limit":  { "annual_inr": 250000, "bpl_only": false },
  "education":     ["class 10"],
  "caste":         ["SC", "ST"],
  "state":         "Tamil Nadu",
  "occupation":    ["farmer"],
  "disability":    false,
  "residence":     "rural"
}
```

### Example PostgreSQL queries

```sql
-- Schemes for women in Tamil Nadu
SELECT name, ministry
FROM schemes
WHERE eligibility_json::jsonb @> '{"gender": "female", "state": "Tamil Nadu"}'::jsonb;

-- Schemes for SC/ST with income limit
SELECT name, (eligibility_json::jsonb -> 'income_limit')
FROM schemes
WHERE (eligibility_json::jsonb -> 'caste') ? 'SC'
  AND ((eligibility_json::jsonb -> 'income_limit' ->> 'annual_inr')::int > 0);

-- Schemes with disability support
SELECT name FROM schemes
WHERE eligibility_json::jsonb @> '{"disability": true}'::jsonb;
```

If you see a `WIN1252` encoding error on `₹` in psql on Windows:

```sql
SET client_encoding = 'UTF8';
```

---

## Calibrating field names

```python
import json
data = json.load(open("data/raw/myscheme_raw.json"))
print(list(data[0].keys()))
```

Update field mappings in `parsers/normalize.py` accordingly.