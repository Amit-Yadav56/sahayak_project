"""
label_tool.py
==============
Interactive CLI tool for manually labeling eligibility text for NER training.

Pre-fills every paragraph with the rule-based extractor's spans so you're
CORRECTING mistakes, not labeling from scratch. In practice this means
most records need only a keypress to accept, with occasional fixes.

Controls:
  Enter / y     → accept all pre-labeled entities for this record
  d <n>         → delete entity number n  (e.g. "d 2" deletes the 2nd entity)
  r <n> <LABEL> → relabel entity n        (e.g. "r 1 INCOME" changes label)
  a <start>:<end> <LABEL> → add new entity by character offset
  s             → skip this record (won't be saved)
  q             → quit and save progress

Progress is auto-saved after every accepted record to:
  data/manual_labels.json

Resume: just re-run — already-labeled records are skipped automatically.
When you reach 50 accepted records, run:
  python label_tool.py --export
to convert manual_labels.json → data/manual_labels.spacy (spaCy DocBin).
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path

from ml.ner_extractor.extractor import extract_entities, _NLP
from spacy.tokens import DocBin

DATA_FILE    = Path("data/processed/schemes_normalized.json")
LABELS_FILE  = Path("data/manual_labels.json")
TARGET       = 100
ENTITY_LABELS = ["AGE", "INCOME", "GENDER", "CATEGORY", "OCCUPATION",
                 "EDUCATION", "REQUIREMENT"]

# ── ANSI colours (skip if terminal doesn't support them) ────────────────────
_USE_COLOR = sys.stdout.isatty() and os.name != "nt"

def _c(text, code):
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

def red(t):    return _c(t, "91")
def green(t):  return _c(t, "92")
def yellow(t): return _c(t, "93")
def cyan(t):   return _c(t, "96")
def bold(t):   return _c(t, "1")
def dim(t):    return _c(t, "2")

LABEL_COLORS = {
    "AGE":         "93",   # yellow
    "INCOME":      "92",   # green
    "GENDER":      "95",   # magenta
    "CATEGORY":    "96",   # cyan
    "OCCUPATION":  "94",   # blue
    "EDUCATION":   "33",   # dark yellow
    "REQUIREMENT": "91",   # red
}

def _color_label(label):
    code = LABEL_COLORS.get(label, "97")
    return _c(f"[{label}]", code)


# ── Record selection ─────────────────────────────────────────────────────────
def select_candidates(records: list, n: int = TARGET * 4) -> list:
    """
    Pick a diverse set of candidates: records that have at least one entity
    the extractor found, are not too long (easier to review), and cover all
    entity label types. We over-select (n = TARGET*3) so the human can skip
    some while still reaching TARGET accepted records.
    """
    random.seed(42)

    def _has_entity(r):
        return bool(extract_entities(r.get("raw_json", {}).get("eligibility", "") or ""))

    # bucket by which entity types appear
    buckets = {label: [] for label in ENTITY_LABELS}
    for r in records:
        text = r.get("raw_json", {}).get("eligibility", "") or ""
        if not text or len(text) > 800:   # skip very long records — harder to review
            continue
        spans = extract_entities(text)
        if not spans:
            continue
        for s in spans:
            buckets[s["label"]].append(r)

    # sample evenly across buckets, then de-duplicate
    seen_slugs = set()
    selected = []
    per_bucket = max(n // len(ENTITY_LABELS), 5)
    for label, recs in buckets.items():
        pool = [r for r in recs if r.get("slug", r.get("source_id", "")) not in seen_slugs]
        for r in random.sample(pool, min(per_bucket, len(pool))):
            slug = r.get("slug", r.get("source_id", ""))
            if slug not in seen_slugs:
                seen_slugs.add(slug)
                selected.append(r)

    random.shuffle(selected)
    return selected[:n]


# ── Display helpers ───────────────────────────────────────────────────────────
def _render_text_with_entities(text: str, entities: list) -> str:
    """
    Annotate the raw text with coloured [LABEL] markers so the human
    can see exactly what span each entity covers.
    """
    sorted_ents = sorted(entities, key=lambda e: e["start"])
    out = []
    cursor = 0
    for e in sorted_ents:
        if e["start"] > cursor:
            out.append(text[cursor:e["start"]])
        marker = _color_label(e["label"])
        out.append(bold(text[e["start"]:e["end"]]) + marker)
        cursor = e["end"]
    out.append(text[cursor:])
    return "".join(out)


def _print_entity_list(entities: list):
    for i, e in enumerate(entities, 1):
        print(f"  {dim(str(i)+'.')} {_color_label(e['label'])}  "
              f"{bold(repr(e['text']))}  "
              f"{dim(f'chars {e[chr(115)]+ e[chr(116)]+ e[chr(97)]+ e[chr(114)]+ e[chr(116)]}')}",
              end="")
    # ↑ that's unnecessarily cute — plain version:

def _print_entity_list(entities: list):
    for i, e in enumerate(entities, 1):
        span_info = f"[{e['start']}:{e['end']}]"
        print(f"  {i}. {_color_label(e['label']):20}  "
              f"{bold(repr(e['text'])):<40}  "
              f"{dim(span_info)}")


# ── Parse edit commands ───────────────────────────────────────────────────────
def _parse_command(line: str, entities: list, text: str):
    """
    Returns the new entity list after applying the command, or None on error.
    Returns the original list unchanged for "y" / Enter.
    """
    line = line.strip()

    if line in ("", "y"):
        return entities  # accept as-is

    if line == "s":
        return "SKIP"

    if line == "q":
        return "QUIT"

    parts = line.split()

    # Find: f <phrase>  — show all offsets where phrase appears in text
    # Makes it painless to add full-phrase entities without counting chars.
    if parts[0] == "f":
        phrase = line[2:].strip()
        if not phrase:
            print(red("  Usage: f <phrase>   e.g.  f master's degree"))
            return None
        import re
        matches = [(m.start(), m.end()) for m in re.finditer(re.escape(phrase), text, re.IGNORECASE)]
        if not matches:
            print(yellow(f"  '{phrase}' not found in text."))
        else:
            print(cyan(f"  '{phrase}' found at:"))
            for s, e in matches:
                print(f"    {s}:{e}   context: ...{repr(text[max(0,s-15):e+15])}...")
            print(cyan(f"  → to label all occurrences: xa <LABEL> {phrase}"))
            print(cyan(f"  → to label by offset:       a {matches[0][0]}:{matches[0][1]} <LABEL>"))
        return None  # don't advance — let user issue the add command next

    # Replace-all: xa START:END LABEL PHRASE
    # Finds every occurrence of PHRASE in text and adds all as LABEL entities.
    # Replaces existing bare-word entities that are substrings of the phrase.
    # Usage: xa 39:53 EDUCATION general degree
    if parts[0] == "xa" and len(parts) >= 3:
        import re
        label = parts[1].upper()
        if label not in ENTITY_LABELS:
            print(red(f"  Unknown label '{label}'. Valid: {ENTITY_LABELS}"))
            return None
        phrase = " ".join(parts[2:])
        matches = [(m.start(), m.end()) for m in re.finditer(re.escape(phrase), text, re.IGNORECASE)]
        if not matches:
            print(yellow(f"  '{phrase}' not found in text."))
            return None
        # Remove existing entities that are fully contained within any of the
        # new spans (e.g. bare 'degree' inside 'general degree')
        new = [e for e in entities if not any(
            s <= e["start"] and e["end"] <= en
            for s, en in matches
        )]
        added = 0
        for s, en in matches:
            new.append({"start": s, "end": en, "label": label, "text": text[s:en]})
            added += 1
        new.sort(key=lambda e: e["start"])
        print(green(f"  Added {added} × {label} {repr(phrase)} (replaced any contained bare-word entities)"))
        return new

    # Delete all of a label: da <LABEL>
    # Clears every entity with a given label in one command.
    # Usage: da EDUCATION
    if parts[0] == "da" and len(parts) == 2:
        label = parts[1].upper()
        before = len(entities)
        new = [e for e in entities if e["label"] != label]
        removed = before - len(new)
        if removed:
            print(yellow(f"  Deleted {removed} {label} entity/entities."))
        else:
            print(yellow(f"  No {label} entities found."))
        return new

    # Delete: d <n>
    if parts[0] == "d" and len(parts) == 2:
        try:
            idx = int(parts[1]) - 1
            if 0 <= idx < len(entities):
                new = entities[:]
                removed = new.pop(idx)
                print(yellow(f"  Deleted: {removed['label']} {repr(removed['text'])}"))
                return new
        except ValueError:
            pass

    # Relabel: r <n> <LABEL>
    if parts[0] == "r" and len(parts) == 3:
        try:
            idx = int(parts[1]) - 1
            new_label = parts[2].upper()
            if 0 <= idx < len(entities) and new_label in ENTITY_LABELS:
                new = [e.copy() for e in entities]
                old_label = new[idx]["label"]
                new[idx]["label"] = new_label
                print(yellow(f"  Relabeled: {old_label} → {new_label}"))
                return new
        except ValueError:
            pass

    # Add: a <start>:<end> <LABEL>
    if parts[0] == "a" and len(parts) == 3:
        try:
            start, end = map(int, parts[1].split(":"))
            label = parts[2].upper()
            if label in ENTITY_LABELS and 0 <= start < end <= len(text):
                new_ent = {
                    "start": start, "end": end,
                    "label": label, "text": text[start:end]
                }
                new = entities + [new_ent]
                new.sort(key=lambda e: e["start"])
                print(green(f"  Added: {label} {repr(text[start:end])}"))
                return new
        except (ValueError, KeyError):
            pass

    print(red("  Unknown command. Try:"))
    print(red("    Enter/y          accept all"))
    print(red("    d N              delete entity N"))
    print(red("    da LABEL         delete all entities with this label"))
    print(red("    r N LABEL        relabel entity N"))
    print(red("    a START:END LAB  add entity by char offset"))
    print(red("    f phrase         find char offsets of a phrase in text"))
    print(red("    xa LABEL phrase  add every occurrence of phrase as LABEL"))
    print(red("    s                skip    q  quit"))
    return None


# ── Main labeling loop ────────────────────────────────────────────────────────
def label(target: int = TARGET):
    records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    candidates = select_candidates(records)

    # Load existing progress
    existing = []
    labeled_slugs = set()
    if LABELS_FILE.exists():
        existing = json.loads(LABELS_FILE.read_text(encoding="utf-8"))
        labeled_slugs = {r["slug"] for r in existing}
        print(green(f"Resuming — {len(existing)} records already labeled."))

    accepted = len(existing)

    print(bold(f"\n{'='*65}"))
    print(bold("  spaCy NER Labeling Tool"))
    print(bold(f"  Target: {target} records   Progress: {accepted}/{target}"))
    print(bold(f"{'='*65}\n"))
    print("Controls:")
    print("  Enter / y            → accept all pre-labeled entities")
    print("  d N                  → delete entity N")
    print("  da LABEL             → delete all entities with a label  (e.g. da EDUCATION)")
    print("  r N LABEL            → relabel entity N                  (e.g. r 1 INCOME)")
    print("  a START:END LABEL    → add entity by char offset")
    print("  f phrase             → find char offsets of a phrase in text")
    print("  xa LABEL phrase      → add every occurrence of phrase as LABEL")
    print("  s                    → skip this record")
    print("  q                    → quit and save\n")

    for rec in candidates:
        if accepted >= target:
            break

        slug = rec.get("slug") or rec.get("source_id") or rec.get("name", "")
        if slug in labeled_slugs:
            continue

        text = rec.get("raw_json", {}).get("eligibility", "") or ""
        if not text.strip():
            continue

        # Pre-fill from rule extractor
        entities = extract_entities(text)
        if not entities:
            continue

        print(f"\n{bold(cyan(f'Record {accepted+1}/{target}'))}  {dim(slug)}")
        print(f"{bold('Scheme:')} {rec.get('name','')[:70]}")
        print(f"{bold('State:')}  {rec.get('state','')}")
        print()
        print(bold("Eligibility text:"))
        print("  " + _render_text_with_entities(text, entities))
        print()
        print(bold("Pre-labeled entities:"))
        _print_entity_list(entities)
        print()

        # Edit loop
        while True:
            try:
                cmd = input(bold("  Command: ")).strip()
            except (EOFError, KeyboardInterrupt):
                cmd = "q"

            result = _parse_command(cmd, entities, text)
            if result is None:
                # Bad command — try again
                continue
            if result == "SKIP":
                print(dim("  Skipped."))
                break
            if result == "QUIT":
                _save(existing)
                print(green(f"\nSaved {len(existing)} records → {LABELS_FILE}"))
                return
            # Accepted (possibly edited)
            entities = result

            # Show updated list if anything changed
            if cmd not in ("", "y"):
                print(bold("\n  Updated entities:"))
                _print_entity_list(entities)
                continue

            # Save
            existing.append({
                "slug": slug,
                "name": rec.get("name", ""),
                "text": text,
                "entities": entities,
                "reviewed": True,
            })
            labeled_slugs.add(slug)
            accepted += 1
            _save(existing)
            print(green(f"  ✓ Saved ({accepted}/{target})"))
            break

    print(bold(green(f"\nDone! {accepted} records labeled → {LABELS_FILE}")))
    if accepted >= target:
        print(f"Run  {bold('python label_tool.py --export')}  to convert to .spacy format.")


def _save(records: list):
    LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    LABELS_FILE.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


# ── Export to spaCy DocBin ────────────────────────────────────────────────────
def export():
    if not LABELS_FILE.exists():
        print(red(f"{LABELS_FILE} not found — run the labeling tool first."))
        return

    records = json.loads(LABELS_FILE.read_text(encoding="utf-8"))
    reviewed = [r for r in records if r.get("reviewed")]
    print(f"Exporting {len(reviewed)} reviewed records to spaCy format...")

    db = DocBin(store_user_data=True)
    skipped = 0
    for rec in reviewed:
        text = rec["text"]
        doc = _NLP.make_doc(text)
        ents = []
        for e in rec["entities"]:
            span = doc.char_span(e["start"], e["end"], label=e["label"],
                                  alignment_mode="contract")
            if span is not None:
                ents.append(span)
        try:
            doc.ents = ents
            db.add(doc)
        except Exception as ex:
            print(yellow(f"  Skipped '{rec['slug']}': {ex}"))
            skipped += 1

    out = Path("data/manual_labels.spacy")
    db.to_disk(out)
    print(green(f"Saved {len(reviewed) - skipped} docs → {out}"))
    print()
    print("To retrain the NER model using manual labels instead of silver labels:")
    print(f"  Edit {bold('generate_training_data.py')} to also include {bold('data/manual_labels.spacy')}")
    print("  Or pass it directly to train_ner.py as a higher-weight training source.")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", action="store_true",
                        help="Convert data/manual_labels.json → data/manual_labels.spacy")
    parser.add_argument("--target", type=int, default=TARGET,
                        help=f"Number of records to label (default: {TARGET})")
    args = parser.parse_args()

    if args.export:
        export()
    else:
        label(target=args.target)