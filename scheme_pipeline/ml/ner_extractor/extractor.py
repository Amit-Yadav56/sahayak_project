"""
ml/ner_extractor/extractor.py
===============================
MODEL 2 — Eligibility Criteria Extractor (rule-based spaCy pipeline)

This is the "no labeled data yet" version: instead of a trained NER model,
it uses spaCy's Matcher with hand-written token patterns to pull structured
entities (AGE, INCOME, CATEGORY, GENDER, OCCUPATION, REQUIREMENT) out of raw
scheme eligibility text.

Why spaCy Matcher instead of plain regex (what parsers/normalize.py used)?
  - Works on TOKENS, not characters — "18 to 60 years" and "18-60 yrs" and
    "between 18 and 60" are all the same pattern shape once tokenized,
    where regex needs a separate alternative for each phrasing.
  - Patterns compose: an AGE pattern and a GENDER pattern can match inside
    the same sentence without one regex needing to know about the other.
  - This Matcher-based pipeline is a drop-in upgrade path: once you have
    even ~200 labeled examples (text + correct eligibility_json), you can
    swap this for spacy.training to fine-tune an actual NER component on
    top of the SAME nlp pipeline object, without touching the surrounding
    code that calls extract().

Usage:
    from ml.ner_extractor.extractor import extract_eligibility

    result = extract_eligibility(
        "The applicant must be female, aged between 18 and 60 years, "
        "belonging to SC/ST/OBC category, with annual family income "
        "below Rs 1,00,000. Must have a valid Aadhar card and bank account."
    )
    # {
    #   "min_age": 18, "max_age": 60, "max_income": 100000,
    #   "categories": ["SC", "ST", "OBC"], "gender": "female",
    #   "occupation": [], "state": "any",
    #   "requires": ["aadhar", "bank_account"]
    # }
"""

import re
import logging
from dataclasses import dataclass, field

import spacy
from spacy.matcher import Matcher
from spacy.tokens import Doc, Span

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── Output schema ───────────────────────────────────────────────────────────

@dataclass
class EligibilityCriteria:
    min_age: int | None = None
    max_age: int | None = None
    max_income: int | None = None
    education: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    gender: str = "any"
    occupation: list[str] = field(default_factory=list)
    state: str = "any"
    disability: bool = False
    is_widow: bool = False
    requires: list[str] = field(default_factory=list)  # ["aadhar", "bank_account", ...]

    def to_dict(self) -> dict:
        return {
            "min_age": self.min_age,
            "max_age": self.max_age,
            "max_income": self.max_income,
            "education": self.education,
            "categories": self.categories,
            "gender": self.gender,
            "occupation": self.occupation,
            "state": self.state,
            "disability": self.disability,
            "is_widow": self.is_widow,
            "requires": self.requires,
        }


# ── Build the spaCy pipeline once (module-level, reused across calls) ────────

def _build_nlp():
    """
    Blank English pipeline + Matcher with hand-written patterns.
    No pretrained weights needed — this only uses the tokenizer and
    rule matching, both of which work on spacy.blank("en").
    """
    nlp = spacy.blank("en")
    matcher = Matcher(nlp.vocab)

    # ── AGE patterns ──────────────────────────────────────────────────────
    # "18 to 60 years" / "18-60 years" / "between 18 and 60"
    matcher.add("AGE_RANGE", [
        [{"LIKE_NUM": True}, {"LOWER": {"IN": ["to", "-", "and"]}}, {"LIKE_NUM": True},
         {"LOWER": {"IN": ["years", "yrs", "year"]}, "OP": "?"}],
        [{"LOWER": "between"}, {"LIKE_NUM": True}, {"LOWER": "and"}, {"LIKE_NUM": True}],
    ])
    # "above 18" / "minimum 18 years" / "at least 18" / "minimum age 21 years"
    # We deliberately do NOT require "years" after the number — many real
    # eligibility sentences write "above 18" with no trailing unit. Instead,
    # the income/age collision (e.g. "income below 2 lakh") is resolved in
    # extract_eligibility() by preferring INCOME_MAX when "income" appears
    # earlier in the same clause — see the disambiguation step below.
    matcher.add("AGE_MIN", [
        [{"LOWER": {"IN": ["above", "minimum", "min", "atleast"]}},
         {"LOWER": "age", "OP": "?"}, {"LIKE_NUM": True}],
        [{"LOWER": "at"}, {"LOWER": "least"}, {"LIKE_NUM": True}],
        [{"LIKE_NUM": True}, {"LOWER": {"IN": ["years", "year", "yrs"]}, "OP": "?"},
         {"LOWER": {"IN": ["and", "or"]}, "OP": "?"}, {"LOWER": "above"}],
    ])
    # "below 60" / "maximum 60 years" / "up to 60" / "upto 60" / "maximum age 60"
    matcher.add("AGE_MAX", [
        [{"LOWER": {"IN": ["below", "maximum", "max", "upto"]}},
         {"LOWER": "age", "OP": "?"}, {"LIKE_NUM": True}],
        [{"LOWER": "up"}, {"LOWER": "to"}, {"LIKE_NUM": True}],
    ])

    # ── INCOME patterns ───────────────────────────────────────────────────
    # "income below Rs 1,00,000" / "income less than ₹50000" / "income not exceeding 2 lakh"
    # / "income should not exceed 1 crore" / "annual income upto 2 lakh"
    matcher.add("INCOME_MAX", [
        [{"LOWER": "income"}, {"OP": "*", "LOWER": {"NOT_IN": ["."]}},
         {"LOWER": {"IN": ["below", "less", "under", "upto", "exceeding", "than", "exceed"]}},
         {"OP": "*"}, {"LIKE_NUM": True}],
    ])
    # "BPL" / "below poverty line"
    matcher.add("BPL", [
        [{"LOWER": "bpl"}],
        [{"LOWER": "below"}, {"LOWER": "poverty"}, {"LOWER": "line"}],
    ])

    # ── CATEGORY patterns (caste/EWS) ────────────────────────────────────
    matcher.add("CATEGORY", [
        [{"TEXT": {"REGEX": r"^(SC|ST|OBC|EWS)$"}}],
    ])

    # ── GENDER patterns ──────────────────────────────────────────────────
    matcher.add("GENDER_FEMALE", [
        [{"LOWER": {"IN": ["female", "females", "women", "woman", "girls", "girl"]}}],
    ])
    matcher.add("GENDER_MALE", [
        [{"LOWER": {"IN": ["male", "males", "men", "man", "boys", "boy"]}}],
    ])

    # ── OCCUPATION patterns ──────────────────────────────────────────────
    matcher.add("OCCUPATION", [
        [{"LOWER": {"IN": [
            "farmer", "farmers", "labourer", "labourers", "laborer", "laborers",
            "fisherman", "fishermen", "fisherwoman", "weaver", "weavers",
            "artisan", "artisans", "student", "students", "widow", "widows",
            "disabled", "construction"
        ]}}],
    ])

    # ── REQUIREMENT patterns (documents/accounts needed) ─────────────────
    matcher.add("REQUIRES_AADHAR", [[{"LOWER": {"IN": ["aadhar", "aadhaar"]}}]])
    matcher.add("REQUIRES_BANK", [
        [{"LOWER": "bank"}, {"LOWER": "account"}],
    ])
    matcher.add("REQUIRES_RATION", [[{"LOWER": "ration"}, {"LOWER": "card"}]])

    # ── EDUCATION patterns ──────────────────────────────────────────────
    matcher.add("EDUCATION_CLASS", [
        [{"LIKE_NUM": True}, {"LOWER": {"IN": ["st", "nd", "rd", "th"]}, "OP": "?"},
         {"LOWER": {"IN": ["standard", "class", "grade", "pass", "passed"]}, "OP": "?"}],
        [{"LOWER": "class"}, {"LIKE_NUM": True}],
        [{"LOWER": "10+2"}],
        [{"LIKE_NUM": True}, {"TEXT": {"REGEX": r"^\+2$"}}],
    ])
    matcher.add("EDUCATION_HIGHER", [
        [{"LOWER": {"IN": ["graduate", "graduation", "postgraduate", "post-graduate", "degree", "diploma", "phd", "mphil"]}}],
        [{"LOWER": "post"}, {"LOWER": {"IN": ["graduate", "graduation"]}}],
        [{"LOWER": "undergraduate"}],
    ])

    return nlp, matcher


_NLP, _MATCHER = _build_nlp()


# ── Number parsing helpers ────────────────────────────────────────────────

def _to_int(token_text: str) -> int | None:
    """Parse a number token, handling Indian-style commas (1,00,000)."""
    cleaned = re.sub(r"[,\s]", "", token_text)
    try:
        return int(cleaned)
    except ValueError:
        return None


def _scale_for_lakh_crore(value: int, span_text: str) -> int:
    """If 'lakh' or 'crore' appears right after the number, scale it."""
    s = span_text.lower()
    if "crore" in s:
        return value * 10_000_000
    if "lakh" in s:
        return value * 100_000
    return value


# ── Main extraction function ──────────────────────────────────────────────

def extract_eligibility(text: str, state_hint: str = "any") -> dict:
    """
    Run the rule-based extractor over raw eligibility text.

    Args:
        text: raw eligibility paragraph (can be semicolon-delimited clauses
              joined, same input style as parsers/normalize.py used)
        state_hint: pass the scheme's known state column value directly —
              state is usually a separate structured field already, not
              worth extracting from free text when you already have it.

    Returns: dict matching EligibilityCriteria.to_dict() shape.
    """
    if not text or not text.strip():
        return EligibilityCriteria(state=state_hint).to_dict()

    doc = _NLP(text)
    matches = _MATCHER(doc)

    result = EligibilityCriteria(state=state_hint)
    categories_found = set()
    occupations_found = set()
    requires_found = set()
    education_found = set()

    # Sort matches by start position so AGE_MIN/AGE_MAX don't overwrite
    # a more specific AGE_RANGE match found earlier in the same span area
    matches = sorted(matches, key=lambda m: m[1])

    age_range_spans = []  # track to avoid double-counting AGE_MIN/MAX inside a range

    # Disambiguation: AGE_MIN/AGE_MAX use "above"/"below"/"minimum"/"maximum",
    # which also appear in income phrasing ("income below 2 lakh"). If the
    # word "income" appears in a small token window around an AGE_MIN/MAX
    # match, treat that match as income-related, not age-related, and skip
    # it — INCOME_MAX will have already captured the actual number correctly.

    def _income_context_nearby(start: int, window: int = 6) -> bool:
        """Check a small token window around a match for the word 'income'."""
        win_start = max(0, start - window)
        win_end = min(len(doc), start + window)
        return "income" in doc[win_start:win_end].text.lower()

    for match_id, start, end in matches:
        label = _NLP.vocab.strings[match_id]
        span: Span = doc[start:end]
        span_text = span.text

        if label == "AGE_RANGE":
            nums = [_to_int(t.text) for t in span if t.like_num]
            nums = [n for n in nums if n is not None]
            if len(nums) >= 2:
                result.min_age, result.max_age = min(nums), max(nums)
                age_range_spans.append((start, end))

        elif (label == "AGE_MIN"
              and not any(s <= start < e for s, e in age_range_spans)
              and not _income_context_nearby(start)):
            nums = [_to_int(t.text) for t in span if t.like_num]
            if nums:
                result.min_age = nums[0]

        elif (label == "AGE_MAX"
              and not any(s <= start < e for s, e in age_range_spans)
              and not _income_context_nearby(start)):
            nums = [_to_int(t.text) for t in span if t.like_num]
            if nums:
                result.max_age = nums[0]

        elif label == "INCOME_MAX":
            nums_in_span = [t.text for t in span if t.like_num]
            if nums_in_span:
                raw_val = _to_int(nums_in_span[-1])  # last number in the matched span
                if raw_val is not None:
                    # check a small window after the match for "lakh"/"crore"
                    window_end = min(end + 3, len(doc))
                    window_text = doc[start:window_end].text
                    result.max_income = _scale_for_lakh_crore(raw_val, window_text)

        elif label == "BPL":
            result.max_income = result.max_income or 0  # BPL implies very low/no income threshold
            requires_found.add("bpl_certificate")

        elif label == "CATEGORY":
            categories_found.add(span_text.upper())

        elif label == "GENDER_FEMALE":
            result.gender = "female"

        elif label == "GENDER_MALE":
            if result.gender != "female":  # don't let a stray "men" downgrade an explicit "female" elsewhere
                result.gender = "male"

        elif label == "OCCUPATION":
            occupations_found.add(span_text.lower())

        elif label == "REQUIRES_AADHAR":
            requires_found.add("aadhar")

        elif label == "REQUIRES_BANK":
            requires_found.add("bank_account")

        elif label == "REQUIRES_RATION":
            requires_found.add("ration_card")

        elif label == "EDUCATION_CLASS":
            lowered = span_text.lower().replace(" ", "")
            if lowered == "10+2" or "+2" in lowered:
                education_found.add("12th standard")
            else:
                education_found.add(span_text.strip())

        elif label == "EDUCATION_HIGHER":
            education_found.add(span_text.strip())

    result.categories = sorted(categories_found)
    result.occupation = sorted(occupations_found)
    result.requires = sorted(requires_found)
    result.education = sorted(education_found)
    result.disability = bool(re.search(r"\bdisab(led|ility)\b", text, re.IGNORECASE))
    result.is_widow = bool(re.search(r"\bwidow", text, re.IGNORECASE))

    return result.to_dict()


# ── Quick CLI test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    samples = [
        
        "The applicant must be female, age 20 years and above "
        "belonging to SC/ST/OBC category, with annual family income "
        "below Rs 1,00,000. Must have a valid Aadhar card and bank account.",

        "Open to BPL families only. The applicant must be a registered "
        "construction worker. Minimum age 21 years.",

        "Any farmer above 20 with a ration card may apply.",

        "The beneficiary must be a resident of Uttarakhand. Open to all genders.",
    ]

    for s in samples:
        print("─" * 70)
        print("INPUT: ", s[:80] + ("..." if len(s) > 80 else ""))
        print("OUTPUT:", extract_eligibility(s))
