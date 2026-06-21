# Scheme Pipeline

Scrapes Indian government schemes from myscheme.gov.in, data.gov.in, and Kaggle,
normalizes eligibility data into a structured JSON format using a rule-based +
trainable-NER extractor, and loads everything into PostgreSQL.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

If you are installing on Python 3.14, make sure pip is pulling a recent pandas
release. Older pandas pins can force a NumPy source build on Windows when no
compatible wheel is available.

`ml/ner_extractor` additionally needs `spacy` (already in `requirements.txt`).
No pretrained spaCy model download is required for the rule-based extractor —
it runs on `spacy.blank("en")`. The trainable NER model (see below) is trained
from scratch on this project's own data, so nothing needs downloading there
either.

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

# Step 2: Parse and normalize (runs ml/ner_extractor under the hood
#          to populate eligibility_json from raw eligibility text)
python -m parsers.normalize --max 10
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
│                            (calls ml/ner_extractor on the raw eligibility text)
│
├── ml/
│   └── ner_extractor/
│       ├── extractor.py          ← MODEL 2: rule-based spaCy Matcher extractor
│       │                            (extract_eligibility, extract_entities)
│       └── __init__.py
│
├── db/
│   ├── schema.sql         ← table DDL + indexes (auto-applied by loader.py)
│   └── loader.py          ← upserts data/processed/schemes_normalized.json → PostgreSQL
│
├── data/
│   ├── raw/               ← raw scraped JSON and CSV files
│   ├── processed/         ← normalized JSON ready for DB (schemes_normalized.json)
│   ├── train.spacy        ← NER training split (generated, see below)
│   ├── dev.spacy          ← NER held-out eval split (generated, see below)
│   └── train_preview.json ← human-readable sample of silver-labeled spans
│
├── trained_model/         ← trained spaCy NER pipeline (generated, see below)
│
├── audit_normalized.py        ← coverage stats + red-flag detection over the full normalized dataset
├── generate_training_data.py  ← converts extractor spans → spaCy train/dev .spacy files
└── train_ner.py                ← trains + evaluates the NER model on held-out dev data
```

---

## ML Model 2 — Eligibility Criteria Extractor

`ml/ner_extractor/extractor.py` turns raw eligibility text into the structured
`eligibility_json` shape. It runs in two parts:

- **AGE / GENDER / CATEGORY / OCCUPATION / EDUCATION / REQUIREMENT** — spaCy
  `Matcher` token patterns, with context guards that reject false positives
  (e.g. "2 to 3 years of experience" isn't an age range; "50% women members"
  on a review panel isn't an applicant gender requirement; numbers outside a
  0–100 plausibility bound are rejected outright — catches things like
  "academic year 2022-23" or "up to 150 units" of electricity).
- **INCOME / BPL** — a separate clause-scoped regex pass, *not* the Matcher.
  Indian government text writes amounts as `₹48,000/-`, which breaks spaCy's
  `like_num` token check, and naive matching tends to cross clause boundaries
  and grab numbers from unrelated sentences. The regex pass handles comma
  formatting (including the stray-space `"₹2, 00,000/-"` variant), `lakh`/
  `lac`/`lahk`/`crore`/`LPA`/`thousand` multipliers, decimal lakhs
  (`"₹2.50 Lakh"`), polarity (`"greater than X"` is a floor, not a ceiling —
  declined rather than mislabeled), `"Non BPL"` exclusion, and skips
  `"Income Tax Act"` boilerplate common in trust/organization eligibility
  text.

```python
from ml.ner_extractor.extractor import extract_eligibility

result = extract_eligibility(scheme["raw_json"]["eligibility"])
# {
#   "min_age": 18, "max_age": 60, "max_income": 250000,
#   "categories": ["SC", "ST"], "gender": "female",
#   "occupation": ["farmer"], "state": "any",
#   "education": [], "disability": False, "is_widow": False,
#   "requires": ["aadhar", "bank_account"]
# }
```

Always feed it the clean, semicolon-delimited `eligibility` field — not the
full scheme description — and make sure clauses stay joined with `"; "`, not
a bare space, when reconstructing text upstream. The false-friend context
guards scan outward to the nearest `;` boundary; collapsing clauses into one
undifferentiated blob silently defeats them.

### Known limitations (not bugs — schema/ambiguity gaps)

- **Monthly vs. annual income.** `max_income` is meant to be annual, but
  some source text only states a monthly figure (e.g. *"income less than
  ₹500/- per month"*). The extractor reports the number as written rather
  than guessing a ×12 conversion. Worth a product decision if you want
  estimated-annual values instead.
- **Two-age-bracket schemes.** A handful of schemes state eligibility for
  two disjoint groups in one record (e.g. *"orphan children below 14"* **and**
  *"elderly above 60"*). `min_age`/`max_age` can't represent two separate
  bands — this needs a schema change (e.g. a list of age brackets), not a
  better regex.
- **`occupation` sometimes contains beneficiary-type values**, not real
  occupations (`"individual"`, `"infra"`, `"family"`). This comes from
  `normalize.py`'s fallback to the raw `beneficiary_type` CSV column when the
  extractor finds nothing — those are beneficiary classifications, not
  occupations, and the field is somewhat overloaded as a result.

### Auditing extraction quality at scale

```bash
python audit_normalized.py
```

Prints per-field coverage (% of records where each `eligibility_json` field
got populated), automated red-flag checks (`age min > max`, implausible ages,
suspiciously small income ceilings), top occupation/caste/education value
distributions, and a random spot-check sample — run this after any change to
`extractor.py` or `normalize.py`, against the full dataset, not a handful of
examples. Several real bugs in this pipeline (clause-crossing income matches,
calendar years read as ages, institutional "years of existence" read as
applicant age) only became visible at full volume — a small sample isn't
enough to trust a change.

---

## Training the NER model

The Matcher/regex extractor above is also a **silver-label generator**: its
own (filtered, non-overlapping) entity spans become training data for a real
spaCy `ner` pipeline component, so the model can generalize past exact rule
wording instead of only matching hand-written patterns.

```bash
# 1. Make sure data/processed/schemes_normalized.json is up to date
python -m parsers.normalize

# 2. Convert it into a train/dev split (90/10) of spaCy training data
python generate_training_data.py
#   → data/train.spacy, data/dev.spacy, data/train_preview.json

# 3. Train + evaluate on the held-out dev set
python train_ner.py
#   → trained_model/  (loadable spaCy pipeline)
```

`train_ner.py` prints precision/recall/F1 per entity label on dev data that
was never seen during training. As of the last full run (4789 records, 3033
train / 336 dev):

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

**Caveat:** the dev set is labeled by the same rule-based extractor the model
trains on (weak/distant supervision). High F1 here means the model learned to
reproduce the rules' decision boundary — useful, since it implies the model
will generalize to phrasing the hand-written patterns don't cover — but it is
**not** a ground-truth accuracy number. Validate against a small
human-checked sample before trusting this for anything beyond what the rules
already do.

```python
import spacy
nlp = spacy.load("trained_model")
doc = nlp("Applicants must be female, aged 18 to 35, with family income below ₹2 lakh")
print([(ent.text, ent.label_) for ent in doc.ents])
```

---

## eligibility_json schema

Every scheme row stores a structured `eligibility_json` JSONB column:

```json
{
  "age":           { "min": 18, "max": 60 },
  "gender":        "female",
  "income_limit":  { "annual_inr": 250000, "bpl_only": false },
  "education":     [],
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
