"""
generate_training_data.py
==========================
Converts each scheme's eligibility text + the v3 extractor's (filtered,
non-overlapping) entity spans into spaCy's native training format, with
a real train/dev split this time — at 4789 records there's enough volume
to actually hold out a dev set and measure precision/recall, instead of
eyeballing predictions on the same handful of examples used for training.

Run:  python3 generate_training_data.py
Output:
  data/train.spacy          (90% split, for training)
  data/dev.spacy            (10% split, held out — for eval only)
  data/train_preview.json   (human-readable sample, for eyeballing labels)
"""

import json
import random
from pathlib import Path

from spacy.tokens import DocBin

from ml.ner_extractor.extractor import extract_entities, _NLP

DATA_FILE = Path("data/processed/schemes_normalized.json")
TRAIN_OUT = Path("data/train.spacy")
DEV_OUT = Path("data/dev.spacy")
PREVIEW_OUT = Path("data/train_preview.json")
DEV_FRACTION = 0.1
SEED = 42


def build_training_docs(records: list[dict]):
    skipped_no_text = 0
    skipped_no_entities = 0

    for rec in records:
        text = rec.get("raw_json", {}).get("eligibility", "")
        if not text or not text.strip():
            skipped_no_text += 1
            continue

        spans = extract_entities(text)
        if not spans:
            skipped_no_entities += 1
            continue

        doc = _NLP.make_doc(text)
        ents = []
        for s in spans:
            ent = doc.char_span(s["start"], s["end"], label=s["label"], alignment_mode="contract")
            if ent is not None:
                ents.append(ent)
        doc.ents = ents

        preview = {
            "scheme": rec.get("name", rec.get("slug", "")),
            "text": text,
            "entities": [{"text": e.text, "label": e.label_, "start": e.start_char, "end": e.end_char}
                         for e in doc.ents],
        }
        yield doc, preview

    print(f"  (skipped {skipped_no_text} record(s) with empty eligibility text)")
    print(f"  (skipped {skipped_no_entities} record(s) where the extractor found nothing)")


def main():
    records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(records)} records from {DATA_FILE}")

    docs, previews = [], []
    for doc, preview in build_training_docs(records):
        docs.append(doc)
        previews.append(preview)

    print(f"Built {len(docs)} training example(s) from {len(records)} record(s).")

    random.seed(SEED)
    shuffled = docs[:]
    random.shuffle(shuffled)
    n_dev = max(1, int(len(shuffled) * DEV_FRACTION))
    dev_docs = shuffled[:n_dev]
    train_docs = shuffled[n_dev:]

    train_bin = DocBin(store_user_data=True)
    for d in train_docs:
        train_bin.add(d)
    dev_bin = DocBin(store_user_data=True)
    for d in dev_docs:
        dev_bin.add(d)

    # Merge manual labels before saving — must happen before to_disk()
    manual_path = Path("data/manual_labels.spacy")
    if manual_path.exists():
        manual_db = DocBin().from_disk(manual_path)
        manual_docs = list(manual_db.get_docs(_NLP.vocab))
        for doc in manual_docs * 5:
            train_bin.add(doc)
        print(f"  + {len(manual_docs)} manual labels (×5 weight) merged into train set")
    else:
        print("  (no manual_labels.spacy found — training on silver labels only)")

    TRAIN_OUT.parent.mkdir(parents=True, exist_ok=True)
    train_bin.to_disk(TRAIN_OUT)
    dev_bin.to_disk(DEV_OUT)
    PREVIEW_OUT.write_text(json.dumps(random.sample(previews, min(20, len(previews))), indent=2, ensure_ascii=False),
                            encoding="utf-8")

    print(f"  train: {len(train_docs)} examples -> {TRAIN_OUT}")
    print(f"  dev:   {len(dev_docs)} examples -> {DEV_OUT}")
    print(f"  preview (20 random examples) -> {PREVIEW_OUT}")

    from collections import Counter
    label_counts = Counter()
    for d in docs:
        for ent in d.ents:
            label_counts[ent.label_] += 1
    print("\nLabel distribution (entity span count, all docs):")
    for label, count in label_counts.most_common():
        print(f"  {label:<12} {count}")


if __name__ == "__main__":
    main()