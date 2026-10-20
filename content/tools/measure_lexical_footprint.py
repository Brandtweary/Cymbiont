"""Estimate the on-disk footprint of precomputed per-article FTS5 lexical tables.

Samples stored articles uniformly from every active native generation and builds
prototype artifacts in the shapes a precompute could write, so the total can be
extrapolated from measurement rather than guessed:

  naive      one FTS5 table per article with its content, plus per-passage build
             material rows, at the spans artifact's 8 KiB pages
  contentless one FTS5 table per article without content, at 512-byte pages with
             optimized segments — the smallest shape that still ranks exactly
  none       the same contentless shape with detail=none, which does not rank
             (bm25 returns -0.0); measured to show it is not an option
  material   a zlib blob per article of the passage build material the search
             path would need beside the index
  rows       a zlib blob per article of the (handle, lexical text) rows alone,
             the rows-only precompute that still builds the table at query time

Run it on the host that holds the corpus, from a deployed content tree, with the
interpreter that runs the service: PYTHONPATH=. python tools/measure_lexical_footprint.py
--data /path/to/content-state --sample 200. Writes scratch databases beside the
report and deletes nothing else.
"""
import argparse
import json
import random
import sqlite3
import time
import zlib
from pathlib import Path

MATERIAL_SCHEMA = """
CREATE TABLE passages(entry_index INTEGER NOT NULL, ordinal INTEGER NOT NULL,
    passage_id TEXT NOT NULL, block_index INTEGER NOT NULL, start INTEGER NOT NULL,
    end INTEGER NOT NULL, text TEXT NOT NULL, kind TEXT NOT NULL, section TEXT NOT NULL,
    page_index INTEGER, page_label TEXT, coordinates TEXT, anchor TEXT, flags TEXT NOT NULL,
    PRIMARY KEY(entry_index, passage_id)) WITHOUT ROWID;
CREATE INDEX passages_ordinal ON passages(entry_index, ordinal);
"""


def new_db(path, page_size):
    for suffix in ("", "-journal"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(f"PRAGMA page_size={page_size}")
    return connection


def material_rows(index, article):
    """Per-passage build material in the row shape the naive artifact stores."""
    blocks, spans = article.blocks, article.spans
    for ordinal, (passage_id, _text) in enumerate(article.rows):
        block_index, start, end, extra = spans[ordinal]
        text, kind, section, page_index, page_label, coordinates, anchor, flags = blocks[block_index]
        yield (index, ordinal, passage_id, block_index, start, end, text, kind, json.dumps(section),
               page_index, page_label,
               json.dumps(coordinates) if coordinates is not None else None,
               anchor, json.dumps(flags + extra))


def blob(payload):
    return zlib.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), 6)


def material_blob(article):
    blocks, spans = article.blocks, article.spans
    return blob([[pid, *spans[ordinal], *blocks[spans[ordinal][0]]]
                 for ordinal, (pid, _text) in enumerate(article.rows)])


def rows_blob(article):
    return blob(article.rows)


def sample_indexes(reader, spans, wanted, rng):
    entries = reader.archive.entry_count
    candidates = rng.sample(range(entries), min(entries, wanted * 4))
    have = [row[0] for row in spans.execute(
        f"SELECT entry_index FROM articles WHERE entry_index IN ({','.join('?' * len(candidates))})",
        candidates)]
    return sorted(have[:wanted])


def measure(store, scratch, wanted, rng, log):
    from oracle_content.native import KIND
    report = {}
    for generation in store.active_generations():
        manifest = store.manifest(generation)
        if manifest.get("kind") != KIND:
            continue
        directory = store.directory(generation)
        spans = sqlite3.connect(f"file:{directory}/article-spans.sqlite?mode=ro", uri=True)
        counted = int(spans.execute("SELECT value FROM meta WHERE key='articles'").fetchone()[0])
        reader = store.native(generation)
        sample = sample_indexes(reader, spans, wanted, rng)
        log(f"=== {generation[:8]} articles={counted} sampled={len(sample)}")
        naive = new_db(scratch / f"{generation[:8]}-naive.sqlite", 8192)
        naive.executescript(MATERIAL_SCHEMA)
        contentless = new_db(scratch / f"{generation[:8]}-contentless.sqlite", 512)
        none = new_db(scratch / f"{generation[:8]}-none.sqlite", 512)
        blob_bytes = {"material": 0, "rows": 0}
        started = time.perf_counter()
        processed = []
        for index in sample:
            article = reader.localizable(reader.document_id(index))
            if not hasattr(article, "blocks"):
                continue
            processed.append(index)
            name = f"t{index}"
            naive.execute(f"CREATE VIRTUAL TABLE {name} USING fts5(id UNINDEXED,text,tokenize='porter unicode61')")
            naive.executemany(f"INSERT INTO {name} VALUES(?,?)", article.rows)
            naive.executemany("INSERT INTO passages VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              material_rows(index, article))
            contentless.execute(f"CREATE VIRTUAL TABLE {name} USING fts5(text,tokenize='porter unicode61',content='')")
            contentless.executemany(f"INSERT INTO {name} VALUES(?)",
                                   [(text,) for _pid, text in article.rows])
            none.execute(f"CREATE VIRTUAL TABLE {name} USING fts5(text,tokenize='porter unicode61',content='',detail='none')")
            none.executemany(f"INSERT INTO {name} VALUES(?)", [(text,) for _pid, text in article.rows])
            blob_bytes["material"] += len(material_blob(article))
            blob_bytes["rows"] += len(rows_blob(article))
        for connection in (naive, contentless, none):
            connection.commit()
            for index in processed:
                try:
                    connection.execute(f"INSERT INTO t{index}(t{index}) VALUES('optimize')")
                except sqlite3.Error:
                    pass
            connection.commit()
            connection.close()
        measured = {"articles": counted, "sampled": len(processed)}
        if not processed:
            report[generation] = measured
            log("no stored articles in the sample; skipped")
            spans.close()
            continue
        for label, path, blob_total in (
                ("naive", scratch / f"{generation[:8]}-naive.sqlite", None),
                ("contentless", scratch / f"{generation[:8]}-contentless.sqlite", None),
                ("none", scratch / f"{generation[:8]}-none.sqlite", None),
                ("material_blob", None, blob_bytes["material"]),
                ("rows_blob", None, blob_bytes["rows"])):
            total = path.stat().st_size if path is not None else blob_total
            measured[label] = {"bytes_per_article": round(total / len(sample), 1),
                               "extrapolated_gib": round(total / len(sample) * counted / 2**30, 2)}
        measured["localize_seconds_per_article"] = round((time.perf_counter() - started) / len(sample), 4)
        report[generation] = measured
        log(json.dumps(measured, indent=2))
        spans.close()
        for path in (scratch / f"{generation[:8]}-naive.sqlite", scratch / f"{generation[:8]}-contentless.sqlite",
                     scratch / f"{generation[:8]}-none.sqlite"):
            path.unlink(missing_ok=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True, help="The content state directory")
    parser.add_argument("--sample", type=int, default=200, help="Articles sampled per generation")
    parser.add_argument("--scratch", type=Path, default=Path("/tmp"),
                        help="Where the prototype databases are written and deleted")
    parser.add_argument("--report", type=Path, default=None, help="Where to write the JSON report")
    parser.add_argument("--seed", type=int, default=20261020)
    args = parser.parse_args()
    from oracle_content.store import Store

    args.scratch.mkdir(parents=True, exist_ok=True)
    report = measure(Store(args.data), args.scratch, args.sample, random.Random(args.seed), print)
    text = json.dumps(report, indent=2)
    if args.report is not None:
        args.report.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
