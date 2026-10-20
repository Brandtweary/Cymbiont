"""How often do bm25 scores tie inside an article's top lexical window?

The search path orders a hit article's passages with `ORDER BY bm25(article), id`,
so a tie is resolved by the passage handle. A contentless precomputed FTS5 table
cannot return the id column, so it can order only by rowid once bm25 ties, and
preserving the ranking exactly then requires fetching and re-tiebreaking the
matched rows. This measures how often that matters on real text: how many
article-query pairs have any bm25 tie inside the top-lexical-depth window, and
how many tie at the window boundary, where the tiebreak decides which passages
the search returns at all.

Run it on the host that holds the corpus, from a deployed content tree, with the
interpreter that runs the service: PYTHONPATH=. python tools/measure_lexical_ties.py
--data /path/to/content-state.
"""
import argparse
import json
import random
import re
import sqlite3
from pathlib import Path

QUERIES = ["water purification methods", "well drilling groundwater", "beekeeping hive management",
           "leather tanning bark", "definition of abrasion", "first aid bandage wound",
           "how to make soap from lye", "herbal medicine preparation", "knot tying",
           "crop rotation soil improvement", "the"]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True, help="The content state directory")
    parser.add_argument("--sample", type=int, default=40, help="Articles sampled per generation")
    parser.add_argument("--depth", type=int, default=40, help="The profile's lexical depth")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    from oracle_content.native import KIND
    from oracle_content.store import Store

    rng = random.Random(args.seed)
    total = tied_window = tied_boundary = 0
    store = Store(args.data)
    for generation in store.active_generations():
        if store.manifest(generation).get("kind") != KIND:
            continue
        reader = store.native(generation)
        entries = reader.archive.entry_count
        candidates = rng.sample(range(entries), min(entries, args.sample * 4))
        with sqlite3.connect(f"file:{store.directory(generation)}/article-spans.sqlite?mode=ro", uri=True) as spans:
            have = [row[0] for row in spans.execute(
                f"SELECT entry_index FROM articles WHERE entry_index IN ({','.join('?' * len(candidates))})",
                candidates)]
        for index in have[:args.sample]:
            article = reader.localizable(reader.document_id(index))
            if not hasattr(article, "blocks"):
                continue
            for query in QUERIES:
                tokens = re.findall(r"[^\W_]+(?:[-./][^\W_]+)*", query)
                expression = " OR ".join('"' + token + '"' for token in tokens)
                memory = sqlite3.connect(":memory:")
                memory.execute("CREATE VIRTUAL TABLE article USING fts5(id UNINDEXED,text,tokenize='porter unicode61')")
                memory.executemany("INSERT INTO article VALUES(?,?)", article.rows)
                rows = memory.execute(
                    "SELECT bm25(article) FROM article WHERE article MATCH ? ORDER BY bm25(article),id LIMIT ?",
                    (expression, args.depth)).fetchall()
                memory.close()
                if not rows:
                    continue
                total += 1
                scores = [score for (score,) in rows]
                if any(left == right for left, right in zip(scores, scores[1:])):
                    tied_window += 1
                if len(scores) == args.depth and scores[-1] == scores[-2]:
                    tied_boundary += 1
    print(json.dumps({"article_query_pairs": total,
                      "with_a_tie_inside_the_window": tied_window,
                      "with_a_tie_at_the_window_boundary": tied_boundary}, indent=2))


if __name__ == "__main__":
    main()
