"""Compare the precomputed lexical ranking against the on-the-fly build on live data.

The unit tests prove the mechanism on fixtures; this proves the artifact a pass
actually wrote on the installed corpus: for a sample of articles the artifact
covers, the ranking with the precomputed tables enabled is compared byte for
byte — handles, scores and the built passages — against the same reader with
the artifact disabled, which builds every table in memory as the search path
did before the precompute existed. Any disagreement is a damaged, stale or
misbuilt artifact and names the article to inspect.

Run it on the host that holds the corpus, from the deployed content tree, with
the interpreter that runs the service: PYTHONPATH=. python tools/verify_lexical_agreement.py
--data /path/to/content-state --sample 50
"""
import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path

QUERIES = ["water", "soil crop rotation", "first aid pressure bandage", "definition of energy",
           "filter sand charcoal boil"]


def covered_sample(reader, wanted, rng):
    """Articles the artifact covers, drawn from the shard tables that exist."""
    from oracle_content.lexical import shard_name, shard_table_count
    width = shard_table_count()
    shards = (reader.archive.entry_count + width - 1) // width
    picked = []
    while len(picked) < wanted:
        shard = rng.randrange(shards)
        path = reader.lexicon.directory / shard_name(shard)
        if not path.is_file():
            continue
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        tables = [row[0][1:] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 't*'") if row[0][1:].isdigit()]
        db.close()
        if tables:
            picked.append(int(rng.choice(tables)))
    return picked


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--generation", action="append", default=[],
                        help="Repeatable; defaults to every active native generation")
    parser.add_argument("--sample", type=int, default=25, help="Articles compared per generation")
    parser.add_argument("--limit", type=int, default=40, help="The lexical depth compared")
    parser.add_argument("--seed", type=int, default=20261021)
    args = parser.parse_args()

    from oracle_content.store import Store
    store = Store(args.data)
    generations = args.generation or [value for value in store.active_generations()
                                      if store.manifest(value).get("kind") == "native-zim-article-v1"]
    rng = random.Random(args.seed)
    failures = 0
    for generation in generations:
        reader = store.native(generation)
        lexicon = getattr(reader, "lexicon", None) if reader is not None else None
        if lexicon is None:
            print(json.dumps({"generation": generation[:8], "skipped": "no artifact"}), flush=True)
            continue
        sampled = covered_sample(reader, args.sample, rng)
        print(f"=== {generation[:8]} sampled={len(sampled)}", flush=True)
        for index in sampled:
            document_id = reader.document_id(index)
            for query in QUERIES:
                reader.lexicon = None
                expected = reader._localize([], query, args.limit, document_id)
                reader.lexicon = lexicon
                actual = reader._localize([], query, args.limit, document_id)
                same = (list(expected) == list(actual)
                        and {pid: row.model_dump() for pid, row in expected.passages.items()}
                        == {pid: row.model_dump() for pid, row in actual.passages.items()}
                        and expected.damaged == actual.damaged)
                if not same:
                    failures += 1
                    print(json.dumps({"article": document_id, "query": query, "agree": False}), flush=True)
        print(json.dumps({"generation": generation[:8], "sampled": len(sampled),
                          "queries_each": len(QUERIES), "agreement": "all" if not failures else "FAILED"}),
              flush=True)
    print(json.dumps({"generations": len(generations), "disagreements": failures}), flush=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
