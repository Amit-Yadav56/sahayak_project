"""
ml/ner_extractor/extractor.py
===============================
MODEL 2 — Eligibility Criteria Extractor (rule-based spaCy pipeline)

v3 — fixes applied after auditing v2 output against the FULL 4789-record
myscheme dataset (v2 was only checked against 4 hand-picked records, which
wasn't enough volume to surface these). Two architectural problems found:

  A. INCOME extraction was built on spaCy Matcher with unbounded "OP: '*'"
     wildcards: `[income] [*] [below/less/exceed/than] [*] [number]`.
     Two compounding bugs:
       1. The wildcards aren't bounded by clause punctuation, so the
          matcher happily matches "income ... exceed Rs 4,000. The
          applicant should not be LESS than 60 years..." as ONE match,
          grabbing 60 (an age, from the next sentence) instead of 4,000.
       2. Indian government text writes amounts as "₹48,000/-" — the
          trailing "/-" makes spaCy's `like_num` return False for that
          token, so even when the matcher landed on the right clause, the
          real number was invisible to it and matching fell through to
          whatever the next LIKE_NUM token down the document happened to
          be (often something irrelevant, like "10%" in an unrelated
          sentence three clauses later).
     Verified against the audit: 177 records had a max_income under ₹1000,
     virtually all garbage from one of the two failure modes above.
     Fix: INCOME is no longer Matcher-based. It's now a clause-scoped
     regex pass (see _extract_income_from_text) that finds amounts via
     direct string parsing, immune to like_num, and never reads past a
     ';' or '.' clause boundary. It also fixes two things v2 didn't even
     attempt: (a) "greater than / more than X" means a MINIMUM income
     requirement, not a ceiling — v2's pattern treated "than" as an
     unconditional max-signal regardless of polarity. (b) "LPA" (lakhs
     per annum) wasn't recognized as a scale multiplier, only "lakh"/
     "crore" literally.

  B. AGE extraction had no plausibility bound and an incomplete
     false-friend list. At full volume this caught: "academic year
     2022-23" as age range 23–2022, "up to 150 units" (electricity
     consumption) as max_age=150, "up to 8 family members" as max_age=8,
     "at least 55% marks" as min_age=55, "minimum of 3.5 acres" mixed
     into age matches, "resident of Gujarat for at least 5 years" (a
     residency duration, not age) as min_age=5, and "age relaxation up
     to 10 years" (an exception clause, not the actual ceiling) as
     max_age=10. 17 records had min_age > max_age as a direct result.
     Fix: (1) any candidate age value outside [0, 100] is rejected
     outright — no real applicant age in this dataset exceeds 100, so
     this alone kills every calendar-year and large-quantity misparse.
     (2) AGE_MIN/AGE_MAX/AGE_RANGE now require "age"/"aged"/"year"/"yrs"
     to actually appear somewhere in the enclosing clause — "Classes 1
     to 12" and "up to 8 family members" have no such word and are now
     skipped outright. (3) the false-friend blacklist grew to also cover
     residency-duration, quota/composition, and relaxation-clause
     wording (see _AGE_FALSE_FRIENDS).

v2 fixes (still in effect, see prior changelog in git history / earlier
chat): EDUCATION_CLASS bare-number bug, AGE/GENDER experience & quota
false-friends, broadened disability vocabulary, residence substring bug
(fixed in parsers/normalize.py, not here).

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


# --- Output schema ---

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


# --- Build the spaCy pipeline once (module-level, reused across calls) ---
#
# NOTE: INCOME_MAX and BPL are no longer Matcher patterns — see module
# docstring point A. They're handled by _extract_income_from_text() instead.

def _build_nlp():
    nlp = spacy.blank("en")
    matcher = Matcher(nlp.vocab)

    # --- AGE patterns ---
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

    # --- CATEGORY patterns (caste/EWS) ---
    matcher.add("CATEGORY", [
        [{"TEXT": {"REGEX": r"^(SC|ST|OBC|EWS)$"}}],
    ])

    # --- GENDER patterns ---
    matcher.add("GENDER_FEMALE", [
        [{"LOWER": {"IN": ["female", "females", "women", "woman", "girls", "girl"]}}],
    ])
    matcher.add("GENDER_MALE", [
        [{"LOWER": {"IN": ["male", "males", "men", "man", "boys", "boy"]}}],
    ])

    # --- OCCUPATION patterns ---
    matcher.add("OCCUPATION", [
        [{"LOWER": {"IN": [
            "farmer", "farmers", "labourer", "labourers", "laborer", "laborers",
            "fisherman", "fishermen", "fisherwoman", "weaver", "weavers",
            "artisan", "artisans", "student", "students", "widow", "widows",
            "disabled", "construction", "sportsperson", "sportspersons", "athlete",
            "athletes", "entrepreneur", "entrepreneurs", "self-employed", "unemployed",
        ]}}],
        # "agricultural" alone matches "agricultural land"/"agricultural produce" —
        # only count it as an OCCUPATION when paired with labourer/worker.
        [{"LOWER": "agricultural"}, {"LOWER": {"IN": ["labourer", "labourers", "laborer", "laborers", "worker", "workers"]}}],
    ])

    # --- REQUIREMENT patterns ---
    matcher.add("REQUIRES_AADHAR", [[{"LOWER": {"IN": ["aadhar", "aadhaar"]}}]])
    matcher.add("REQUIRES_BANK", [[{"LOWER": "bank"}, {"LOWER": "account"}]])
    matcher.add("REQUIRES_RATION", [[{"LOWER": "ration"}, {"LOWER": "card"}]])

    # --- EDUCATION patterns ---
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

# --- AGE false-friend / context-guard vocab ---
# Any of these appearing in the enclosing clause disqualifies an AGE match —
# they signal the number means something other than applicant age.
_AGE_FALSE_FRIENDS = {
    "experience", "working", "worked", "work", "service", "served", "tenure",
    "resident", "residing", "domicile",                       # residency duration, not age
    "relax", "relaxation", "relaxable",                        # exception clauses, not the real ceiling
    "marks", "attendance", "%", "percent",                     # academic thresholds
    "member", "members", "acre", "acres", "unit", "units",     # quantities, not age
    "consumption", "kilowatt", "electricity", "land", "cattle",
    "staff", "team", "committee", "panel", "comprise", "comprising",
    "production", "productions", "performance", "existence", "admission",
    "accreditation", "institute", "institution", "department", "proposal",
    "proposals", "project", "grant", "sanctioned", "laboratory",
    "registered", "organisation", "organization",              # institutional tenure, not applicant age
    "priority", "preference",                                  # tie-breaker clauses about a different person (e.g. dependents)
}
# Require one of these to actually be present for an AGE match to count at
# all — "Classes 1 to 12" and "up to 8 family members" have no age/year
# word anywhere nearby and would otherwise slip through.
_AGE_CONTEXT_RE = re.compile(r"\bage\b|\baged\b|\byears?\b|\byrs?\b")
# No real applicant age in govt scheme eligibility text exceeds this — used
# to reject calendar years ("2022-23"), unit counts ("150 units"), etc.
_AGE_PLAUSIBLE_MAX = 100

_COMPOSITION_FALSE_FRIENDS = {"members", "staff", "team", "committee", "panel", "comprise", "comprising", "%"}

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


def _to_number(text: str) -> float | None:
    """Like _to_int but tolerates a decimal point (for '2.50 Lakh' style
    amounts, which _AMOUNT_RE can now capture)."""
    cleaned = re.sub(r"[,\s]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _window_text(doc, start: int, end: int, window: int = 6) -> str:
    win_start = max(0, start - window)
    win_end = min(len(doc), end + window)
    return doc[win_start:win_end].text.lower()


_CLAUSE_BOUNDARY = {";"}


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


# --- INCOME extraction — clause-scoped regex, NOT spaCy Matcher ---
# See module docstring point A for why. Operates directly on the raw text
# string, never crosses a ';' or '.' clause boundary, and parses amounts by
# direct regex rather than relying on spaCy's like_num (which fails on
# "₹48,000/-" style trailing punctuation common in Indian govt text).

# Amount: either comma-grouped digits ("1,50,000" / "2, 00,000" — note we
# tolerate a stray space after the comma, seen in real data), a bare digit
# run ("4000", "60"), or a decimal ("2.50" as in "₹2.50 Lakh p.a."). The
# decimal alternative is listed first so "2.50" isn't short-circuited to
# just "2" by the bare-digit-run alternative.
_AMOUNT_RE = re.compile(r"(\d+\.\d+|\d+(?:,\s?\d{2,3})+|\d+)(?:\s*/-)?\s*(lakh|lakhs|lahk|lahks|lac|lacs|crore|crores|lpa|thousand)?", re.IGNORECASE)

# Phrases that mean "this number is a ceiling" (what we want for max_income).
_INCOME_MAX_INDICATOR_RE = re.compile(
    r"(not\s+exceed(?:ing)?|should\s+not\s+exceed|(?:not|no)\s+more\s+than|less\s+than|\bbelow\b|\bunder\b|up\s*to|maximum\s+of)",
    re.IGNORECASE,
)
# "greater than X" / "more than X" (without a preceding "not"/"no") means X
# is a MINIMUM income requirement — the opposite of what max_income models.
# We don't have a field for that yet, so we just decline to extract rather
# than silently mislabeling a floor as a ceiling.
_INCOME_MIN_PHRASE_RE = re.compile(r"\b(greater\s+than|more\s+than)\b", re.IGNORECASE)
_NEGATED_MORE_THAN_RE = re.compile(r"\b(not|no)\s+more\s+than\b", re.IGNORECASE)

_INCOME_WORD_RE = re.compile(r"\bincome\b", re.IGNORECASE)
_INCOME_TAX_ACT_RE = re.compile(r"\bincome\s+tax\s+act\b", re.IGNORECASE)
_BPL_WORD_RE = re.compile(r"\bbpl\b", re.IGNORECASE)
_NON_BPL_RE = re.compile(r"\b(non|not)[\s-]?bpl\b", re.IGNORECASE)


def _real_income_mentions(clause: str):
    """Yield 'income' word matches that aren't part of the 'Income Tax
    Act' boilerplate reference — extremely common in trust/organization
    eligibility text (citing which section of the Act they're registered
    under), never an actual applicant income threshold. Without this,
    "...registered under section 12AA of the Income Tax Act..." reads
    "under" as a max-indicator and "12" as the income ceiling."""
    for m in _INCOME_WORD_RE.finditer(clause):
        if _INCOME_TAX_ACT_RE.match(clause, m.start()):
            continue
        yield m


def _scale_amount(value: float, multiplier_word: str | None) -> int:
    mw = (multiplier_word or "").lower()
    if mw.startswith("crore"):
        return round(value * 10_000_000)
    if mw.startswith("lakh") or mw.startswith("lac") or mw.startswith("lahk") or mw == "lpa":
        return round(value * 100_000)
    if mw.startswith("thousand"):
        return round(value * 1_000)
    return round(value)


def _iter_clauses(text: str):
    """Yield (clause_text, char_start, char_end) for each ';'-delimited
    clause, with char offsets into the ORIGINAL text (so they can be mapped
    back to spaCy token spans for NER training export).

    Deliberately splits ONLY on ';', not '.' — this dataset's clauses are
    already reliably ';'-delimited (confirmed across hundreds of records),
    and splitting on '.' as well breaks decimal amounts ("₹2.50 Lakh")
    and abbreviations ("p.a.", "Rs.") into separate fragments, which
    silently truncates the real number mid-parse."""
    for m in re.finditer(r"[^;]+", text):
        clause = m.group(0)
        if clause.strip():
            yield clause, m.start(), m.end()


def _extract_income_from_text(text: str):
    """
    Returns (max_income: int|None, char_start: int|None, char_end: int|None,
    bpl_only: bool, bpl_char_span: tuple|None).

    Scans clause-by-clause (never across a ';'/'.' boundary) for income
    ceiling language. Takes the FIRST qualifying clause, left to right.
    """
    max_income = None
    income_span = None
    bpl_only = False
    bpl_span = None

    for clause, c_start, c_end in _iter_clauses(text):
        # BPL detection — but "Non BPL" / "Not BPL" means the OPPOSITE of
        # BPL-only eligibility, so explicitly exclude that first.
        if _BPL_WORD_RE.search(clause) and not _NON_BPL_RE.search(clause):
            if not bpl_only:
                bpl_only = True
                bm = _BPL_WORD_RE.search(clause)
                bpl_span = (c_start + bm.start(), c_start + bm.end())

        if max_income is not None:
            continue  # already found the income ceiling, keep scanning only for BPL

        income_match = next(_real_income_mentions(clause), None)
        if not income_match:
            continue

        # Search for the indicator (and the amount) only AFTER "income"
        # appears — searching from clause start let unrelated phrases like
        # "defined UNDER section 56 of the Income Tax Act" match "under"
        # as if it were an income indicator, grabbing 56 instead of the
        # real income figure (or none at all, for clauses with no real
        # income threshold). Same root cause let "up to 18 years of age"
        # win over "up to ₹72,000" income in a clause mentioning both.
        search_from = income_match.end()

        # "not more than" / "no more than" must be checked BEFORE the bare
        # "more than" disqualifier, since it's a negated (= max) form of it.
        negated = _NEGATED_MORE_THAN_RE.search(clause, search_from)
        bare_min_phrase = _INCOME_MIN_PHRASE_RE.search(clause, search_from)
        if bare_min_phrase and not (negated and negated.start() <= bare_min_phrase.start() <= negated.end()):
            continue  # "greater than X" / "more than X" — a floor, not a ceiling; skip

        indicator = _INCOME_MAX_INDICATOR_RE.search(clause, search_from)
        if not indicator:
            continue

        amt = _AMOUNT_RE.search(clause, indicator.end())
        if not amt:
            continue
        raw_val = _to_number(amt.group(1))
        if raw_val is None or raw_val == 0:
            continue
        max_income = _scale_amount(raw_val, amt.group(2))
        income_span = (c_start + amt.start(), c_start + amt.end())

    return max_income, income_span, bpl_only, bpl_span


# Maps the fine-grained Matcher pattern names to coarser NER entity
# labels suitable for training a real spaCy `ner` component on.
_ENTITY_LABEL_MAP = {
    "AGE_RANGE": "AGE",
    "AGE_MIN": "AGE",
    "AGE_MAX": "AGE",
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
    """Greedily keep the longest, then earliest, non-overlapping spans."""
    spans = sorted(spans, key=lambda s: (-(s[1] - s[0]), s[0]))
    accepted: list[tuple[int, int, str]] = []
    for start, end, label in spans:
        if any(not (end <= a_start or start >= a_end) for a_start, a_end, _ in accepted):
            continue
        accepted.append((start, end, label))
    return sorted(accepted, key=lambda s: s[0])


def _age_value_ok(*nums: int) -> bool:
    return all(0 <= n <= _AGE_PLAUSIBLE_MAX for n in nums)


def _extract(text: str, state_hint: str = "any"):
    """
    Shared internal pass: runs the Matcher for everything except income,
    runs the clause-scoped regex pass for income/BPL, applies all the
    false-friend/plausibility filters, and returns BOTH the resolved
    EligibilityCriteria dataclass AND the raw (start_token, end_token,
    entity_label) spans that survived filtering — the latter feeds the
    NER training-data generator.
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

    # --- Income / BPL (regex pass, char-offset based) ---
    max_income, income_char_span, bpl_only, bpl_char_span = _extract_income_from_text(text)
    result.max_income = max_income
    if bpl_only:
        requires_found.add("bpl_certificate")
    if income_char_span:
        sp = doc.char_span(*income_char_span, alignment_mode="expand")
        if sp is not None:
            entity_spans.append((sp.start, sp.end, "INCOME"))
    if bpl_char_span:
        sp = doc.char_span(*bpl_char_span, alignment_mode="expand")
        if sp is not None:
            entity_spans.append((sp.start, sp.end, "INCOME"))

    # --- Everything else (Matcher pass) ---
    matches = sorted(matches, key=lambda m: m[1])
    age_range_spans = []

    for match_id, start, end in matches:
        label = _NLP.vocab.strings[match_id]
        span: Span = doc[start:end]
        span_text = span.text

        if label == "AGE_RANGE":
            ctx = _clause_text(doc, start, end)
            if not _AGE_CONTEXT_RE.search(ctx) or any(w in ctx for w in _AGE_FALSE_FRIENDS):
                continue
            nums = [_to_int(t.text) for t in span if t.like_num]
            nums = [n for n in nums if n is not None]
            if len(nums) >= 2 and _age_value_ok(*nums):
                result.min_age, result.max_age = min(nums), max(nums)
                age_range_spans.append((start, end))
                entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "AGE_MIN" and not any(s <= start < e for s, e in age_range_spans):
            ctx = _clause_text(doc, start, end)
            if not _AGE_CONTEXT_RE.search(ctx) or any(w in ctx for w in _AGE_FALSE_FRIENDS):
                continue
            nums = [n for n in (_to_int(t.text) for t in span if t.like_num) if n is not None]
            if nums and _age_value_ok(nums[0]):
                result.min_age = nums[0]
                entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "AGE_MAX" and not any(s <= start < e for s, e in age_range_spans):
            ctx = _clause_text(doc, start, end)
            if not _AGE_CONTEXT_RE.search(ctx) or any(w in ctx for w in _AGE_FALSE_FRIENDS):
                continue
            nums = [n for n in (_to_int(t.text) for t in span if t.like_num) if n is not None]
            if nums and _age_value_ok(nums[0]):
                result.max_age = nums[0]
                entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "CATEGORY":
            categories_found.add(span_text.upper())
            entity_spans.append((start, end, _ENTITY_LABEL_MAP[label]))

        elif label == "GENDER_FEMALE":
            ctx = _clause_text(doc, start, end)
            if any(w in ctx for w in _COMPOSITION_FALSE_FRIENDS):
                continue
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
              scheme description.
        state_hint: pass the scheme's known state column directly.
    """
    result, _, _ = _extract(text, state_hint)
    return result.to_dict()


def extract_entities(text: str) -> list[dict]:
    """
    Same extraction pass as extract_eligibility(), but returns the
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
    samples = {
        "Tea plantation (was: age 3-2028 from 'academic year 2022-23')":
            "The applicant must be a tea manufacturing unit.; The applicant must have pursued a final year "
            "undergraduate degree course during the academic year 2022-23.",

        "Veteran Artists (was: max_income=60, picked up an unrelated age)":
            "The personal income of the applicant (including the income of the spouse) must not exceed ₹4,000/- "
            "per month or an annual income of ₹48,000/-.; The applicant should not be less than 60 (sixty) years "
            "of age (This does not apply in the case of a spouse).",

        "Udyogini Scheme (was: max_income=10, grabbed '10%' from a later sentence)":
            "The family income of the applicant should be less than ₹ 1,50,000/- for women belonging to general "
            "and special categories.; About 10% of the allocated target has been earmarked to benefit applicants.",

        "Destitute Children (was: max_income=2, broke on '₹2, 00,000/-' stray-space comma format)":
            "Income of parents/guardians from all sources should not exceed ₹2, 00,000/- per annum.",

        "Relief Fund (was: max_income=2, should DECLINE — 'greater than' is a floor, not a ceiling)":
            "The applicant should be Non BPL.; The Annual Income of the Family should be greater than 2 LPA.",

        "Classes 1 to 12 (was: false age range 1-12)":
            "The applicant should be a student From Classes 1 to 12.; The applicant should maintain at least 50% "
            "attendance to continue receiving benefits.",

        "Family members / acres (was: max_age=8 from 'up to 8 family members')":
            "The applicant must be at least 21 years of age.; The applicant must possess a minimum of 3.5 acres "
            "of agricultural land.; The applicant can apply for up to 8 units.",

        "Age relaxation (was: max_age=10 from the relaxation clause, not the real ceiling)":
            "The applicant must be at least 40 years old (age relaxation up to 10 years for medically retired "
            "athletes).",

        "Residency duration (was: min_age=5 from 'resident ... for at least 5 years')":
            "The applicant should be a domicile of Delhi or a bonafide resident of Delhi for at least 5 years.; "
            "The applicant should be below 30 years old as of the cutoff date.",
    }

    for label, text in samples.items():
        print("─" * 70)
        print(label)
        print(extract_eligibility(text))
