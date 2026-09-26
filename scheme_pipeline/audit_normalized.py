"""
audit_normalized.py
=====================
Sanity-checks data/processed/schemes_normalized.json at full volume:
  1. Coverage stats per eligibility_json field (how often is it populated?)
  2. Automated red-flag detection — implausible values that likely indicate
     a remaining extraction bug (impossible ages, suspiciously common
     values, age min > max, etc.)
  3. A random sample dump for manual spot-checking.
"""
import json
import random
from collections import Counter
from pathlib import Path

DATA_FILE = Path("data/processed/schemes_normalized.json")
records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
print(f"Total records: {len(records)}\n")

# --- Coverage stats ---
n = len(records)
has_age = sum(1 for r in records if r["eligibility_json"]["age"]["min"] or r["eligibility_json"]["age"]["max"])
has_income = sum(1 for r in records if r["eligibility_json"]["income_limit"]["annual_inr"] or r["eligibility_json"]["income_limit"]["bpl_only"])
has_gender = sum(1 for r in records if r["eligibility_json"]["gender"] != "all")
has_caste = sum(1 for r in records if r["eligibility_json"]["caste"])
has_occupation = sum(1 for r in records if r["eligibility_json"]["occupation"])
has_disability = sum(1 for r in records if r["eligibility_json"]["disability"])
has_education = sum(1 for r in records if r["eligibility_json"]["education"])
has_residence = sum(1 for r in records if r["eligibility_json"]["residence"] != "all")

print("COVERAGE (% of records where this field was populated):")
print(f"  age:        {has_age:>5} ({100*has_age/n:.1f}%)")
print(f"  income:     {has_income:>5} ({100*has_income/n:.1f}%)")
print(f"  gender:     {has_gender:>5} ({100*has_gender/n:.1f}%)")
print(f"  caste:      {has_caste:>5} ({100*has_caste/n:.1f}%)")
print(f"  occupation: {has_occupation:>5} ({100*has_occupation/n:.1f}%)")
print(f"  disability: {has_disability:>5} ({100*has_disability/n:.1f}%)")
print(f"  education:  {has_education:>5} ({100*has_education/n:.1f}%)")
print(f"  residence:  {has_residence:>5} ({100*has_residence/n:.1f}%)")

# --- Red flags ---
print("\nRED FLAGS:")

# 1. age min > max (logically impossible)
bad_age_order = [r for r in records
                  if r["eligibility_json"]["age"]["min"] and r["eligibility_json"]["age"]["max"]
                  and r["eligibility_json"]["age"]["min"] > r["eligibility_json"]["age"]["max"]]
print(f"  age min > max:                {len(bad_age_order)} records")

# 2. implausible ages (>110 or negative — likely a misparsed number, e.g. a year or amount)
implausible_age = [r for r in records
                    if (r["eligibility_json"]["age"]["min"] or 0) > 110
                    or (r["eligibility_json"]["age"]["max"] or 0) > 110]
print(f"  age > 110 (likely misparse):  {len(implausible_age)} records")

# 3. implausible income (negative, zero stored as real ceiling, or absurdly small like <100)
suspicious_income = [r for r in records
                      if r["eligibility_json"]["income_limit"]["annual_inr"]
                      and 0 < r["eligibility_json"]["income_limit"]["annual_inr"] < 1000]
print(f"  income ceiling < ₹1000 (likely misparse): {len(suspicious_income)} records")

# 4. occupation / category value distribution — look for junk tokens
occ_counter = Counter()
for r in records:
    occ_counter.update(r["eligibility_json"]["occupation"])
print(f"\n  Top 20 occupation values found:")
for val, cnt in occ_counter.most_common(20):
    print(f"    {cnt:>5}  {val!r}")

caste_counter = Counter()
for r in records:
    caste_counter.update(r["eligibility_json"]["caste"])
print(f"\n  Caste/category value distribution:")
for val, cnt in caste_counter.most_common(20):
    print(f"    {cnt:>5}  {val!r}")

edu_counter = Counter()
for r in records:
    edu_counter.update(r["eligibility_json"]["education"])
print(f"\n  Education value distribution (top 20):")
for val, cnt in edu_counter.most_common(20):
    print(f"    {cnt:>5}  {val!r}")

gender_counter = Counter(r["eligibility_json"]["gender"] for r in records)
print(f"\n  Gender distribution: {dict(gender_counter)}")

residence_counter = Counter(r["eligibility_json"]["residence"] for r in records)
print(f"  Residence distribution: {dict(residence_counter)}")

# --- Random spot-check sample ---
print("\n" + "=" * 78)
print("RANDOM SPOT-CHECK SAMPLE (10 records):")
random.seed(42)
sample = random.sample([r for r in records if r.get("raw_json", {}).get("eligibility")], min(10, n))
for r in sample:
    elig_text = r["raw_json"].get("eligibility", "")
    print("-" * 78)
    print(r["name"][:70])
    print("  TEXT:", elig_text[:200].replace("\n", " "))
    print("  JSON:", json.dumps(r["eligibility_json"], ensure_ascii=False))
