"""
ml/ner_extractor/extractor.py
===============================
MODEL 2 — Eligibility Criteria Extractor (rule-based spaCy pipeline)

v2 — fixes applied after auditing output against real myscheme data:

  1. EDUCATION_CLASS no longer matches bare numbers. The original pattern
     made BOTH suffix tokens ("st/nd/rd/th" AND "standard/class/...")
     optional, so any lone number (an age, an income, a percentage)
     satisfied the whole pattern. Ages like "10 to 19" and incomes like
     "10,000" were leaking into the education list. Fixed by requiring
     the standard/class/grade/pass word to be present.

  2. AGE_RANGE now has the same "is this actually about something else"
     context guard that AGE_MIN/AGE_MAX already had for income. Clauses
     like "experience... for at least 2 to 3 years" were being read as
     an applicant age range. We now skip AGE_RANGE matches that have
     "experience", "working", "service", or similar in a small window
     before the match — these signal duration-of-experience, not age.

  3. GENDER_FEMALE / GENDER_MALE now require the match to NOT be inside
     a composition/quota clause (e.g. "team must comprise 50% women
     members", "at least 30% female staff"). Those describe a hiring
     panel, not applicant eligibility. Heuristic: skip if a percent
     sign/number + "members"/"staff"/"team"/"committee"/"panel" appears
     in the surrounding window.

  4. Disability detection extended beyond \\bdisab(led|ility)\\b to also
     catch "impair(ed|ment)", "deaf", "blind", "pwd", "divyang",
     "handicap(ped)?" — the literal word "disabled" frequently doesn't
     appear in the eligibility clause itself (e.g. "visually or
     hearing-impaired").

  5. Intended input: raw_json["eligibility"] (the clean, semicolon-
     delimited clause field), NOT the full description/benefits text.
     Running over description text reintroduces exactly the kind of
     noise (benefit amounts, step numbers) the patterns above guard
     against, so always extract from the eligibility field specifically.

Usage:
    from ml.ner_extractor.extractor import extract_eligibility

    result = extract_eligibility(scheme["raw_json"]["eligibility"])
"""

import re
import logging
from dataclasses import dataclass, field

import spacy
from spacy.matcher import Matcher
from spacy.tokens import Span

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
    requires: list[str] = field(default_factory=list)

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
    nlp = spacy.blank("en")
    matcher = Matcher(nlp.vocab)

    # ── AGE patterns ──────────────────────────────────────────────────────
    matcher.add("AGE_RANGE", [
        [{"LIKE_NUM": True}, {"LOWER": {"IN": ["to", "-", "and"]}}, {"LIKE_NUM": True},
         {"LOWER": {"IN": ["years", "yrs", "year"]}, "OP": "?"}],
        [{"LOWER": "between"}, {"LIKE_NUM": True}, {"LOWER": "and"}, {"LIKE_NUM": True}],
    ])
    matcher.add("AGE_MIN", [
        [{"LOWER": {"IN": ["above", "minimum", "min", "atleast"]}},
         {"LOWER": "age", "OP": "?"}, {"LIKE_NUM": True}],
        [{"LOWER": "at"}, {"LOWER": "least"}, {"LIKE_NUM": True}],
        [{"LIKE_NUM": True}, {"LOWER": {"IN": ["years", "year", "yrs"]}, "OP": "?"},
         {"LOWER": {"IN": ["and", "or"]}, "OP": "?"}, {"LOWER": "above"}],
    ])
    matcher.add("AGE_MAX", [
        [{"LOWER": {"IN": ["below", "maximum", "max", "upto"]}},
         {"LOWER": "age", "OP": "?"}, {"LIKE_NUM": True}],
        [{"LOWER": "up"}, {"LOWER": "to"}, {"LIKE_NUM": True}],
    ])

    # ── INCOME patterns ───────────────────────────────────────────────────
    matcher.add("INCOME_MAX", [
        [{"LOWER": "income"}, {"OP": "*", "LOWER": {"NOT_IN": ["."]}},
         {"LOWER": {"IN": ["below", "less", "under", "upto", "exceeding", "than", "exceed"]}},
         {"OP": "*"}, {"LIKE_NUM": True}],
    ])
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

    # ── REQUIREMENT patterns ──────────────────────────────────────────────
    matcher.add("REQUIRES_AADHAR", [[{"LOWER": {"IN": ["aadhar", "aadhaar"]}}]])
    matcher.add("REQUIRES_BANK", [[{"LOWER": "bank"}, {"LOWER": "account"}]])
    matcher.add("REQUIRES_RATION", [[{"LOWER": "ration"}, {"LOWER": "card"}]])

    # ── EDUCATION patterns ──────────────────────────────────────────────
    # FIX #1: suffix word is now REQUIRED, not optional — a bare number
    # alone must never satisfy this pattern.
    matcher.add("EDUCATION_CLASS", [
        [{"LIKE_NUM": True}, {"LOWER": {"IN": ["st", "nd", "rd", "th"]}, "OP": "?"},
         {"LOWER": {"IN": ["standard", "class", "grade", "pass", "passed"]}}],
        [{"LOWER": "class"}, {"LIKE_NUM": True}],
        [{"LOWER": "10+2"}],
        [{"LIKE_NUM": True}, {"TEXT": {"REGEX": r"^\+2$"}}],
    ])
    matcher.add("EDUCATION_HIGHER", [
        [{"LOWER": {"IN": ["graduate", "graduation", "postgraduate", "post-graduate",
                            "degree", "diploma", "phd", "mphil"]}}],
        [{"LOWER": "post"}, {"LOWER": {"IN": ["graduate", "graduation"]}}],
        [{"LOWER": "undergraduate"}],
    ])

    return nlp, matcher


_NLP, _MATCHER = _build_nlp()

# FIX #2/#3 context-guard vocab
_AGE_RANGE_FALSE_FRIENDS = {"experience", "working", "worked", "work", "service", "served", "tenure"}
_COMPOSITION_FALSE_FRIENDS = {"members", "staff", "team", "committee", "panel", "comprise", "comprising", "%"}

# FIX #4: broader disability vocabulary
_DISABILITY_RE = re.compile(
    r"\bdisab(led|ility)\b|\bimpair(ed|ment)\b|\bdeaf\b|\bblind\b|\bpwd\b|\bdivyang\b|\bhandicap(ped)?\b",
    re.IGNORECASE,
)


def _to_int(token_text: str) -> int | None:
    cleaned = re.sub(r"[,\s]", "", token_text)
    try:
        return int(cleaned)
    except ValueError:
        return None


def _scale_for_lakh_crore(value: int, span_text: str) -> int:
    s = span_text.lower()
    if "crore" in s:
        return value * 10_000_000
    if "lakh" in s:
        return value * 100_000
    return value


def _window_text(doc, start: int, end: int, window: int = 6) -> str:
    win_start = max(0, start - window)
    win_end = min(len(doc), end + window)
    return doc[win_start:win_end].text.lower()


_CLAUSE_BOUNDARY = {";", "."}


def _clause_text(doc, start: int, end: int) -> str:
    """Expand outward to the enclosing clause (bounded by ';' or '.')
    rather than a fixed token window — false-friend words like
    'experience' can sit many tokens before the number they qualify."""
    clause_start = start
    while clause_start > 0 and doc[clause_start - 1].text not in _CLAUSE_BOUNDARY:
        clause_start -= 1
    clause_end = end
    while clause_end < len(doc) and doc[clause_end].text not in _CLAUSE_BOUNDARY:
        clause_end += 1
    return doc[clause_start:clause_end].text.lower()


# Maps the fine-grained Matcher pattern names to coarser NER entity
# labels suitable for training a real spaCy `ner` component on.
_ENTITY_LABEL_MAP = {
    "AGE_RANGE": "AGE",
    "AGE_MIN": "AGE",
    "AGE_MAX": "AGE",
    "INCOME_MAX": "INCOME",
    "BPL": "INCOME",
    "CATEGORY": "CATEGORY",
    "GENDER_FEMALE": "GENDER",
    "GENDER_MALE": "GENDER",
    "OCCUPATION": "OCCUPATION",
    "REQUIRES_AADHAR": "REQUIREMENT",
    "REQUIRES_BANK": "REQUIREMENT",
    "REQUIRES_RATION": "REQUIREMENT",
    "EDUCATION_CLASS": "EDUCATION",
    "EDUCATION_HIGHER": "EDUCATION",
}


def _resolve_overlaps(spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Greedily keep the longest, then earliest, non-overlapping spans.
    spaCy training entities must not overlap, but AGE_RANGE and AGE_MIN
    can both fire on overlapping token ranges before this step."""
    spans = sorted(spans, key=lambda s: (-(s[1] - s[0]), s[0]))
    accepted: list[tuple[int, int, str]] = []
    for start, end, label in spans:
        if any(not (end <= a_start or start >= a_end) for a_start, a_end, _ in accepted):
            continue
        accepted.append((start, end, label))
    return sorted(accepted, key=lambda s: s[0])


def _extract(text: str, state_hint: str = "any"):
    """
    Shared internal pass: runs the Matcher once, applies all the
    false-friend filters, and returns BOTH the resolved
    EligibilityCriteria dataclass AND the raw (start_token, end_token,
    entity_label) spans that survived filtering — the latter is what
    feeds the NER training-data generator.
    """
    result = EligibilityCriteria(state=state_hint)
    if not text or not text.strip():
        return result, [], None

    doc = _NLP(text)
    matches = _MATCHER(doc)

    categories_found = set()
    occupations_found = set()
    requires_found = set()
    education_found = set()
    entity_spans: list[tuple[int, int, str]] = []  # (start_token, end_token, NER label)

    matches = sorted(matches, key=lambda m: m[1])
    age_range_spans = []

    def _income_context_nearby(start: int, window: int = 6) -> bool:
        win_start = max(0, start - window)
        win_end = min(len(doc), start + window)
        return "income" in doc[win_start:win_end].text.lower()

    for match_id, start, end in matches:
        label = _NLP.vocab.strings[match_id]
        span: Span = doc[start:end]
        span_text = span.text

        if label == "AGE_RANGE":
            ctx = _clause_text(doc, start, end)
            if any(w in ctx for w in _AGE_RANGE_FALSE_FRIENDS):
                continue  # FIX #2: "2 to 3 years" of experience, not age
            nums = [_to_int(t.text) for t in span if t.like_num]
            nums = [n for n in nums if n is not None]
            if len(nums) >= 2:
                result.min_age, result.max_age = min(nums), max(nums)
                age_range_spans.append((start, end))
                entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif (label == "AGE_MIN"
              and not any(s <= start < e for s, e in age_range_spans)
              and not _income_context_nearby(start)
              and not any(w in _clause_text(doc, start, end) for w in _AGE_RANGE_FALSE_FRIENDS)):
            nums = [_to_int(t.text) for t in span if t.like_num]
            if nums:
                result.min_age = nums[0]
                entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif (label == "AGE_MAX"
              and not any(s <= start < e for s, e in age_range_spans)
              and not _income_context_nearby(start)
              and not any(w in _clause_text(doc, start, end) for w in _AGE_RANGE_FALSE_FRIENDS)):
            nums = [_to_int(t.text) for t in span if t.like_num]
            if nums:
                result.max_age = nums[0]
                entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "INCOME_MAX":
            nums_in_span = [t.text for t in span if t.like_num]
            if nums_in_span:
                raw_val = _to_int(nums_in_span[-1])
                if raw_val is not None:
                    window_end = min(end + 3, len(doc))
                    window_text = doc[start:window_end].text
                    result.max_income = _scale_for_lakh_crore(raw_val, window_text)
                    entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "BPL":
            result.max_income = result.max_income or 0
            requires_found.add("bpl_certificate")
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "CATEGORY":
            categories_found.add(span_text.upper())
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "GENDER_FEMALE":
            ctx = _clause_text(doc, start, end)
            if any(w in ctx for w in _COMPOSITION_FALSE_FRIENDS):
                continue  # FIX #3: "50% women members" on a panel, not applicant
            result.gender = "female"
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "GENDER_MALE":
            ctx = _clause_text(doc, start, end)
            if any(w in ctx for w in _COMPOSITION_FALSE_FRIENDS):
                continue
            if result.gender != "female":
                result.gender = "male"
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "OCCUPATION":
            occupations_found.add(span_text.lower())
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "REQUIRES_AADHAR":
            requires_found.add("aadhar")
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "REQUIRES_BANK":
            requires_found.add("bank_account")
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "REQUIRES_RATION":
            requires_found.add("ration_card")
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "EDUCATION_CLASS":
            lowered = span_text.lower().replace(" ", "")
            if lowered == "10+2" or "+2" in lowered:
                education_found.add("12th standard")
            else:
                education_found.add(span_text.strip())
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "EDUCATION_HIGHER":
            education_found.add(span_text.strip())
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

    result.categories = sorted(categories_found)
    result.occupation = sorted(occupations_found)
    result.requires = sorted(requires_found)
    result.education = sorted(education_found)
    result.disability = bool(_DISABILITY_RE.search(text))
    result.is_widow = bool(re.search(r"\bwidow", text, re.IGNORECASE))

    entity_spans = _resolve_overlaps(entity_spans)
    return result, entity_spans, doc


def extract_eligibility(text: str, state_hint: str = "any") -> dict:
    """
    Run the rule-based extractor over eligibility text.

    Args:
        text: should be the clean clause-delimited eligibility text
              (e.g. scheme["raw_json"]["eligibility"]), not the full
              scheme description — see module docstring point 5.
        state_hint: pass the scheme's known state column directly.
    """
    result, _, _ = _extract(text, state_hint)
    return result.to_dict()


def extract_entities(text: str) -> list[dict]:
    """
    Same matcher pass as extract_eligibility(), but returns the
    underlying (filtered, non-overlapping) entity spans as CHARACTER
    offsets — the format spaCy training needs:
        [{"start": 12, "end": 19, "label": "AGE", "text": "18 to 60"}, ...]
    """
    _, entity_spans, doc = _extract(text)
    if doc is None:
        return []
    out = []
    for start, end, label in entity_spans:
        span = doc[start:end]
        out.append({
            "start": span.start_char,
            "end": span.end_char,
            "label": label,
            "text": span.text,
        })
    return out


if __name__ == "__main__":
    # Real eligibility clauses pulled from your sample merged data, to
    # verify the fixes against the bugs that were found.
    samples = {
        "I-MESA-SA (was: min_age=2,max_age=3, gender=female, education had stray numbers)":
            "The applicant must have experience of working with the Social Audit Unit for at least 2 to 3 years.; "
            "The applicant must have experience facilitating social audits of schemes apart from the Mahatma Gandhi "
            "National Rural Employment Guarantee Act.; The team Coordinator leading the team must preferably have "
            "completed a 30 days' certificate course on social accountability and social audit.; The applicant must "
            "ensure the representation of the Scheduled Castes and Other Backward Classes community and the "
            "especially abled in the team.; The team must preferably comprise 50% women members.; The applicant "
            "should have experience working with the elderly, children, victims of substance abuse, and experience "
            "working in rehabilitative institutions.; Anganwadi workers, Accredited Social Health Activists, Civil "
            "Society Organization representatives, or para-legal volunteers working in that area can be included in "
            "the team for community support and mobilization.; Students/Interns from academic institutions can be "
            "engaged as members of the Social Justice Cell after being trained.",

        "ASYF1HVIDSSTITI (was: disability=False, education=['100'])":
            "The applicant must be a student.; The applicant must be 100% visually or hearing-impaired.; The "
            "applicant must be admitted to an Industrial Training Institute.; The applicant must not have received "
            "admission into any Government Hostel.; The applicant must not have received assistance from any "
            "Government Department.",

        "MPMPMSA (was: education=['10,000'])":
            "The martyred soldier must be a permanent resident of Madhya Pradesh.; The applicant must be the mother "
            "or father of a martyred soldier.; The martyred soldier whose death has been recognized as a battle "
            "casualty by the Government of Madhya Pradesh.; The annual income of the applicant's parents must be "
            "less than ₹10,000.",

        "KSPC (was: education=['10','19'])":
            "The beneficiary must be an adolescent between 10 and 19 years of age from Uttarakhand.",
    }

    for label, text in samples.items():
        print("─" * 70)
        print(label)
        print(extract_eligibility(text))
