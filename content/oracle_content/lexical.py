"""Precomputed per-article FTS5 tables for compact native generations.

A lexical search ranks the passages of each article it reaches inside a
per-article in-memory FTS5 table, and building that table — the stored spans
decode, the row construction, the insert — is the cost the first touch of a
novel article pays. This module moves the table itself to a one-time pass over
the generation and serves it from disk: a first touch opens a shard and matches.

Ranking is preserved exactly. The stored table holds the same passage rows in
the same order — its rowid is the passage's ordinal plus one — under the same
tokenizer, and the on-the-fly query's within-article tie-break
(`ORDER BY bm25(article), id`) becomes `ORDER BY bm25(table), rowid` here. The
two orders agree because a passage handle's variable part is the big-endian
coordinate tuple `(block_index, start, end)`, which segmentation emits in
ordinal order, so handle order and rowid order are the same sequence within an
article. The builder refuses to store an article whose handles do not sort in
ordinal order, so the equivalence is checked per article rather than assumed,
and the query path falls back to the in-memory build for any article the
artifact does not cover — absent, damaged, or bound to something else.

The artifact is a directory of shard databases, each holding at most
`SHARD_ARTICLES` per-article virtual tables beside a binding row. A shard is
written whole under a building name and moved into place, so the artifact only
ever grows by the appearance of a complete file: an interrupted pass leaves the
shards it finished published and the rest to the query path, and a resumed pass
simply skips the shards that are already there.
"""
from __future__ import annotations
import fcntl
import json
import os
import shutil
import sqlite3
import threading
import time
import zlib
from collections import OrderedDict
from pathlib import Path

from .precompute import BLOCK_FIELDS, StoredPassages, binding as spans_binding, decode_stored

SCHEMA = "native-article-lexical-v1"
DIRECTORY = "article-lexical"
LOCKNAME = "article-lexical.lock"
STATUS = "article-lexical.status.json"
# The tables are written by the SQLite library that builds them, and a change
# to the tokenizer or the ranking arithmetic between versions would rank the
# same rows differently, so the library version is part of the binding.
PAGE_SIZE = 512

# An article's decoded spans, kept per reader and reused across searches the
# way the in-memory table they replaced was: the decode is a search's cost,
# paid once per article per reader lifetime rather than once per search. The
# byte estimate is the payload's compressed length times the ratio the
# decomposition typically expands it by, so a whole book counts as one.
ROWS_DOCUMENTS = 2048
ROWS_BYTES = 1024 * 1024 * 1024
ROWS_EXPANSION = 6


def shard_name(shard: int) -> str:
    return f"shard-{shard:05d}.sqlite"


def binding(reader) -> dict:
    """What the stored tables depend on, so a changed generation is never reused.

    The spans binding already covers everything the rows depend on — source
    bytes, extraction revision, selection policy, the encoder and segmentation
    fingerprints — because the artifact is built from the spans artifact's own
    payloads, so it is carried whole and the lexical schema and the sharding
    are added beside it.
    """
    return {**spans_binding(reader), "schema": SCHEMA, "sqlite": sqlite3.sqlite_version,
            "shard_articles": shard_table_count()}


def shard_table_count() -> int:
    """Archive indexes per shard.

    Small shards keep a new virtual table cheap to create — the cost of one
    grows with the schema already in the file — and a published shard quick to
    open, while a search never needs more than its lexical depth of them.
    """
    return 256


class LexicalArticle:
    """One article's localization served from its precomputed table.

    Holds the shard connection and the article's identity; the stored spans
    come from the lexicon's decoded-rows cache, and only the passages the
    ranking keeps are built."""

    def __init__(self, lexicon, reader, document, index, db, table):
        self.lexicon, self.reader, self.document, self.index = lexicon, reader, document, index
        self.db, self.table = db, table
        self.found = {}

    def candidates(self, expression, limit):
        """The passage handles the on-the-fly build would rank, in the same order."""
        ordinals = []
        if expression:
            with self.lexicon.lock:
                ordinals = [row[0] - 1 for row in self.db.execute(
                    f"SELECT rowid FROM {self.table} WHERE {self.table} MATCH ?"
                    f" ORDER BY bm25({self.table}), rowid LIMIT ?", (expression, limit))]
        rows = self.lexicon.rows(self.reader, self.document, self.index)
        if not ordinals:
            ordinals = range(min(limit, len(rows.spans)))
        ids = rows.ids(ordinals)
        self.found = dict(zip(ids, ordinals))
        return ids

    def passages(self, ids):
        rows = self.lexicon.rows(self.reader, self.document, self.index)
        return {passage_id: rows.passage(self.found[passage_id]) for passage_id in ids}


class LazySpans:
    """An article's stored spans, decoded once and materialized per passage.

    Localization ranks every passage of an article but keeps only a page of
    them; building every passage as a validated row in order to rank them is
    what first-touch cost. The payload is parsed once here, and only the
    passages the ranking keeps are built, exactly as `StoredPassages` builds
    them, from the same stored form."""

    def __init__(self, reader, document, index):
        from .native import handle
        payload = reader.spans.payload(index)
        if payload is None:
            raise ValueError("the article has no stored spans")
        raw = json.loads(zlib.decompress(payload))
        self.blocks, self.spans = raw[0], raw[1]
        self.estimated_bytes = len(payload) * ROWS_EXPANSION
        self.handle = handle
        self.document, self.index, self.generation = document, index, reader.generation
        self.profile, self.tokenizer = reader.profile, reader.tokenizer

    def id(self, ordinal):
        block_index, start, end = self.spans[ordinal][:3]
        text = self.blocks[block_index][0]
        return self.handle(self.generation, self.index, block_index, start, end, text[start:end])

    def ids(self, ordinals):
        return [self.id(ordinal) for ordinal in ordinals]

    def passage(self, ordinal):
        from .models import Block
        from .precompute import rebuild_passage
        span = self.spans[ordinal]
        row = rebuild_passage(self.document, self.generation, self.index, ordinal,
                              Block(**dict(zip(BLOCK_FIELDS, self.blocks[span[0]]))), span,
                              self.profile, self.tokenizer)
        row.previous = self.id(ordinal - 1) if ordinal else None
        row.next = self.id(ordinal + 1) if ordinal + 1 < len(self.spans) else None
        return row


class ArticleLexicon:
    """Read-side access to one generation's precomputed per-article tables.

    Connections are held in one bounded LRU behind a lock rather than per
    thread: the lexical admission gate already serializes ranking, and the
    lock keeps the tables safe for any concurrency above it. A shard that is
    absent, unreadable, or bound to something else reads as an article the
    artifact does not cover, and the count keeps read failures visible.
    """

    def __init__(self, directory: Path, expected: dict, opened: int = 64):
        self.directory = Path(directory) / DIRECTORY
        self.expected = expected
        self.opened = opened
        self.lock = threading.Lock()
        self.shards: OrderedDict[int, sqlite3.Connection] = OrderedDict()
        self.decoded: OrderedDict[int, LazySpans] = OrderedDict()
        self.decoded_bytes = 0
        self.undecodable = 0

    def rows(self, reader, document, index):
        """The article's decoded spans, kept and reused while they fit the ceiling.

        A search pays the decode once per article per reader lifetime; the
        bound is an estimate, so it keeps the footprint honest rather than
        exact. An article evicted mid-search is only absent from the cache —
        the search that holds it keeps its reference.
        """
        with self.lock:
            held = self.decoded.get(index)
            if held is not None:
                self.decoded.move_to_end(index)
                return held
        rows = LazySpans(reader, document, index)
        with self.lock:
            self.decoded[index] = rows
            self.decoded_bytes += rows.estimated_bytes
            while self.decoded and (len(self.decoded) > ROWS_DOCUMENTS
                                    or self.decoded_bytes > ROWS_BYTES):
                self.decoded_bytes -= self.decoded.popitem(last=False)[1].estimated_bytes
            return rows

    def article(self, reader, document, index):
        """The article's precomputed ranking state, or None when the artifact does not cover it."""
        shard = index // shard_table_count()
        with self.lock:
            db = self._connect(shard)
            if db is None:
                return None
            table = f"t{index}"
            try:
                covered = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                     (table,)).fetchone() is not None
            except sqlite3.Error:
                self.undecodable += 1
                return None
            if not covered:
                return None
            return LexicalArticle(self, reader, document, index, db, table)

    def _connect(self, shard):
        """The shard's connection, or None; called under the lock."""
        db = self.shards.get(shard)
        if db is not None:
            self.shards.move_to_end(shard)
            return db
        path = self.directory / shard_name(shard)
        if not path.is_file():
            return None
        connection = None
        try:
            # The reader serves requests from `asyncio.to_thread` pool threads, so a
            # cached connection is routinely opened by one worker thread and reused by
            # another. Every access is serialized under `self.lock`, which is the
            # synchronization sqlite requires of connections shared across threads.
            connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, check_same_thread=False)
            connection.execute("PRAGMA cache_size=-64")
            stored = connection.execute("SELECT value FROM meta WHERE key='binding'").fetchone()
            if stored is None or json.loads(stored[0]) != self.expected:
                connection.close()
                return None
        except (OSError, sqlite3.Error, ValueError):
            self.undecodable += 1
            if connection is not None:
                connection.close()
            return None
        self.shards[shard] = connection
        while len(self.shards) > self.opened:
            self.shards.popitem(last=False)[1].close()
        return connection


def write_shard(reader, spans, directory: Path, expected: dict, first: int, stop: int, *, commit=32):
    """Build one shard database whole, publishing it only by moving it into place.

    Each covered article's rows come from the same `StoredPassages`
    construction the query path uses, so what is stored is what the in-memory
    build would insert. An article the pass cannot store — excluded by policy,
    without stored spans, or whose handles do not sort in ordinal order — is
    left to the query path, which answers for it as it always has.
    """
    from .models import ContentError
    generation = reader.generation
    shard = first // shard_table_count()
    final = Path(directory) / shard_name(shard)
    building = Path(directory) / (shard_name(shard) + ".building")
    building.unlink(missing_ok=True)
    db = sqlite3.connect(building)
    tables = []
    covered = skipped = failures = 0
    sample = []
    try:
        db.execute(f"PRAGMA page_size={PAGE_SIZE}")
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO meta VALUES('binding',?)",
                   (json.dumps(expected, sort_keys=True, separators=(",", ":")),))
        db.execute("INSERT INTO meta VALUES('shard',?)", (str(shard),))
        for index in range(first, stop):
            payload = spans.payload(index)
            if payload is None:
                skipped += 1
                continue
            table = f"t{index}"
            try:
                blocks, stored = decode_stored(payload)
                document = reader.document(reader.document_id(index))
                article = StoredPassages(document, generation, index, blocks, stored,
                                         reader.profile, reader.tokenizer)
                ids = [passage_id for passage_id, _text in article.rows]
                if ids != sorted(ids):
                    raise ValueError("passage handles do not sort in ordinal order")
                db.execute(f"CREATE VIRTUAL TABLE {table} USING fts5(text,tokenize='porter unicode61',content='')")
                db.executemany(f"INSERT INTO {table}(rowid, text) VALUES(?,?)",
                               [(ordinal + 1, text) for ordinal, (_passage_id, text) in enumerate(article.rows)])
            except ContentError:
                # An article the source's own policy excludes, or whose bytes
                # are quarantined, is refused by the query path too; storing it
                # would rank something no search can reach.
                skipped += 1
            except Exception as error:
                failures += 1
                sample.append([index, type(error).__name__, str(error)[:400]])
                del sample[:64:]
                try:
                    db.execute(f"DROP TABLE IF EXISTS {table}")
                except sqlite3.Error:
                    pass
                continue
            tables.append(table)
            covered += 1
            if covered % commit == 0:
                db.commit()
        for table in tables:
            db.execute(f"INSERT INTO {table}({table}) VALUES('optimize')")
        db.commit()
    finally:
        db.close()
    descriptor = os.open(building, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(building, final)
    handle = os.open(Path(directory), os.O_RDONLY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)
    return {"shard": shard, "covered": covered, "skipped": skipped, "failures": failures,
            "failure_sample": sample[:16], "bytes": final.stat().st_size}


_worker_reader = None


def _worker(root: str, generation: str):
    """One reader per worker process, with its spans usable for row construction."""
    global _worker_reader
    from .native import NativeReader
    from .store import Store
    if (_worker_reader is None or _worker_reader.generation != generation
            or str(_worker_reader.store.root) != root):
        _worker_reader = NativeReader(Store(Path(root)), generation)
    return _worker_reader


def _status(store, generation, state):
    from .store import atomic_json
    atomic_json(store.directory(generation) / STATUS, state)


def _build_shard(root: str, generation: str, directory: str, expected: dict, first: int, stop: int):
    """One shard, built in a worker process from the spans the generation already holds."""
    reader = _worker(root, generation)
    spans = reader.usable_spans()
    if spans is None:
        return {"shard": first // shard_table_count(), "state": "no_spans", "covered": 0,
                "skipped": 0, "failures": 0, "failure_sample": [], "bytes": 0}
    return write_shard(reader, spans, Path(directory), expected, first, stop)


def build_lexical(store, generation, *, workers=1, log=print, min_free_bytes=8 * 1024 ** 3,
                  stop_after_shards=None):
    """Build or resume one generation's per-article lexical tables.

    Shards already published are skipped, so a run interrupted for any reason
    resumes where the last complete shard ended. Each result is logged as it
    lands — covered articles, rate, remaining shards — and recorded in a status
    file beside the artifact, so an unattended run can be read after the fact.
    The pass refuses to take the content state below `min_free_bytes`.
    """
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    from .native import NativeReader

    reader = NativeReader(store, generation)
    spans = reader.usable_spans()
    if spans is None:
        raise ValueError("The lexical precompute requires the generation's article spans")
    expected = binding(reader)
    entries = reader.archive.entry_count
    width = shard_table_count()
    directory = store.directory(generation) / DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    total = -(-entries // width)
    state = {"generation": generation, "state": "starting", "shards_total": total,
             "shards_done": 0, "covered_articles": 0, "failed_articles": 0}
    with (directory / LOCKNAME).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pending = [shard for shard in range(total) if not (directory / shard_name(shard)).is_file()]
        if stop_after_shards is not None:
            pending = pending[:stop_after_shards]
        state["shards_pending"] = len(pending)
        if not pending:
            state["state"] = "complete"
            _status(store, generation, state)
            log(json.dumps(state))
            return state
        started, at_start = time.monotonic(), total - len(pending)
        executor = (ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
                    if workers > 1 else None)
        sample = []

        def record(result):
            nonlocal sample
            state["shards_done"] += 1
            state["covered_articles"] += result["covered"]
            state["failed_articles"] += result["failures"]
            state["artifact_bytes"] = state.get("artifact_bytes", 0) + result["bytes"]
            sample.extend(result["failure_sample"])
            del sample[:64:]
            state["failure_sample"] = sample[:16]
            elapsed = max(time.monotonic() - started, 1e-9)
            remaining = state["shards_total"] - at_start - state["shards_done"]
            state.update({"state": "running",
                          "articles_per_second": round(state["covered_articles"] / elapsed, 1),
                          "shards_remaining": remaining,
                          "remaining_hours": round(remaining * elapsed / state["shards_done"] / 3600, 2),
                          "free_bytes": shutil.disk_usage(store.root).free})
            _status(store, generation, state)
            log(json.dumps({key: value for key, value in state.items() if key != "failure_sample"}))

        terminal, error = "complete", None
        try:
            if executor is None:
                for shard in pending:
                    first = shard * width
                    result = _build_shard(str(store.root), generation, str(directory), expected,
                                           first, min(first + width, entries))
                    record(result)
                    if shutil.disk_usage(store.root).free < min_free_bytes:
                        terminal, error = "stopped_low_disk", "free space reached the configured floor"
                        break
            else:
                # A bounded submission window keeps the free-space floor a live
                # check rather than one taken before hours of queued work.
                window = max(1, workers * 2)
                submitted, collected, in_flight = 0, 0, []
                while collected < len(pending):
                    while submitted < len(pending) and len(in_flight) < window:
                        shard = pending[submitted]
                        first = shard * width
                        in_flight.append((shard, executor.submit(_build_shard, str(store.root), generation,
                                                                str(directory), expected, first,
                                                                min(first + width, entries))))
                        submitted += 1
                    _shard, future = in_flight.pop(0)
                    record(future.result())
                    collected += 1
                    if shutil.disk_usage(store.root).free < min_free_bytes:
                        terminal, error = "stopped_low_disk", "free space reached the configured floor"
                        break
        except BaseException as exception:
            terminal = "stopped_by_signal" if isinstance(exception, (KeyboardInterrupt, SystemExit)) else "failed"
            error = f"{type(exception).__name__}: {exception}"
            raise
        finally:
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)
            state["state"] = terminal
            if error is not None:
                state["error"] = error
            _status(store, generation, state)
        return state
