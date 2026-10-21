"""The precomputed per-article lexical tables must rank exactly as the built ones do."""
import json
import threading
import zlib
from collections import OrderedDict
from types import SimpleNamespace

import pytest

from oracle_content.extract import segment
from oracle_content.lexical import (ArticleLexicon, DIRECTORY, binding as lexical_binding,
                                     shard_table_count, write_shard)
from oracle_content.models import Block, Passage
from oracle_content.native import NativeReader, span_handle
from oracle_content.precompute import ArticleSpans, binding as spans_binding, encode
from tests.test_precompute import Tokens, document, profile, write_artifact


def lead(document, generation, index):
    built = Passage(passage_id="", document_id=document.document_id, source_revision=document.sha256,
                    extraction_revision=document.extraction_revision, ordinal=0, block_index=0xFFFFFFFF,
                    start=0, end=10, text="Solar coo", embedding_text="passage: Solar Cooker\nSolar coo",
                    section=[], kind="article_lead",
                    page={"index": None, "label": None, "coordinates": None, "anchor": None},
                    flags=["text_omitted", "title_lead_semantic_representation"])
    built.passage_id = span_handle(generation, index, built)
    return built


def tie_blocks(seed):
    """Blocks whose passages tie: one uniform text that splits into identical spans,
    repeated across two blocks so the tie spans a block boundary too."""
    uniform = " ".join(["filter water sand charcoal"] * 600)
    return [
        Block(text=f"Article {seed} about water purification and sand filters.", kind="paragraph",
              section=["Overview"]),
        Block(text=uniform, kind="paragraph", section=["Method"], flags=["figure_requires_visual_inspection"]),
        Block(text=uniform, kind="paragraph", section=["Method", "Notes"]),
        Block(text=" | ".join(f"cell{n}" for n in range(300)), kind="table", section=["Data"],
              flags=["table_headers_unverified"]),
        Block(text=f"A closing note {seed} about boiling water.", kind="list_item", section=["Data"]),
    ]


class Corpus:
    """A generation directory with its spans artifact, and readers over it.

    `payloads` replaces the segmented form, so a test can store spans the
    segmentation would not produce."""

    def __init__(self, tmp_path, specs, generation="f" * 64, shards=None, payloads=None):
        self.generation = generation
        self.settings, self.tokens = profile(), Tokens()
        documents = {}
        if payloads is None:
            payloads = {}
            for index, structure in specs.items():
                doc = document().model_copy(update={"document_id": f"z_{'c' * 64}_{index}"})
                passages = segment(doc, structure, self.settings, self.tokens, generation)
                for row in passages:
                    row.passage_id = span_handle(generation, index, row)
                for ordinal, row in enumerate(passages):
                    row.previous = passages[ordinal - 1].passage_id if ordinal else None
                    row.next = passages[ordinal + 1].passage_id if ordinal + 1 < len(passages) else None
                payloads[index] = encode(structure, passages, lead(doc, generation, index), None)
                documents[index] = doc
        else:
            documents = {index: document().model_copy(update={"document_id": f"z_{'c' * 64}_{index}"})
                         for index in payloads}
        self.documents = documents
        self.spans_dir = tmp_path / "spans"
        self.spans_dir.mkdir()
        self.expected = spans_binding(self._stub())
        write_artifact(self.spans_dir, self.expected, payloads)
        self.directory = tmp_path / "generation"
        (self.directory / DIRECTORY).mkdir(parents=True)
        self.spans = ArticleSpans.open(self.spans_dir, self.expected)
        self.binding = lexical_binding(self.reader(False))
        if shards is None:
            shards = sorted({index // shard_table_count() for index in payloads})
        self.results = [write_shard(self.reader(True), self.spans, self.directory / DIRECTORY, self.binding,
                                    shard * shard_table_count(), (shard + 1) * shard_table_count())
                        for shard in shards]

    def _stub(self):
        """The reader attributes a binding reads, before the full reader exists."""
        stub = SimpleNamespace(generation=self.generation,
                               template=SimpleNamespace(sha256="c" * 64, extraction_revision="html-structural-v4"),
                               representation="title-lead-v2", policy="canonical-html",
                               profile=self.settings)
        return stub

    def reader(self, with_lexicon):
        reader = NativeReader.__new__(NativeReader)
        reader.profile, reader.tokenizer = self.settings, self.tokens
        reader.template = self._stub().template
        reader.representation = "title-lead-v2"
        reader.policy = "canonical-html"
        reader.generation = self.generation
        reader.spans = self.spans
        reader.usable_spans = lambda: reader.spans
        reader.lexicon = ArticleLexicon(self.directory, self.binding) if with_lexicon else None
        reader.document_id = lambda index: f"z_{'c' * 64}_{index}"
        reader.document = lambda document_id: self.documents[int(document_id.rsplit("_", 1)[1])]
        reader.archive = SimpleNamespace(get_entry_by_path=lambda path: SimpleNamespace(is_redirect=False,
                                                                                         _index=int(path)))
        reader.admit_entry = lambda index: None
        reader.cache, reader.document_cache = OrderedDict(), OrderedDict()
        reader.cache_bytes = 0
        reader.cache_lock = threading.RLock()
        reader.lexical_states, reader.lexical_state_bytes = OrderedDict(), 0
        reader.verify_original = lambda: None
        return reader


def assert_identical(actual, expected):
    assert list(actual) == list(expected)
    assert ({pid: row.model_dump() for pid, row in actual.passages.items()}
            == {pid: row.model_dump() for pid, row in expected.passages.items()})


@pytest.mark.parametrize("with_paths", [False, True])
@pytest.mark.parametrize("query,limit", [
    ("filter water", 5), ("water", 40), ("sand charcoal filter water", 3),
    ("cell0 cell1", 2), ("nothing matches these words", 7), ("", 6), ("water purification", 1)])
def test_precomputed_tables_rank_identically_to_the_built_tables(tmp_path, with_paths, query, limit):
    """The artifact's whole point is that a first touch answers exactly as the
    on-the-fly build would: same handles, same scores, same built passages, for
    the same article set. The uniform-text article guarantees bm25 ties inside
    the result window, so the within-article tie-break is compared too."""
    specs = {3: tie_blocks(1), 260: tie_blocks(2), 513: tie_blocks(3), 700: tie_blocks(4)}
    corpus = Corpus(tmp_path, specs)
    reference, precomputed = corpus.reader(False), corpus.reader(True)
    # The comparison is only evidence if the artifact actually serves the articles;
    # a reader that silently fell back would agree with itself for free.
    for index in specs:
        assert precomputed.lexicon.article(precomputed, corpus.documents[index], index) is not None
    # The fixture must actually hold a tie, or it proves nothing about the tie-break.
    tied = [text for _pid, text in reference.localizable("z_" + "c" * 64 + "_260").rows]
    assert len(tied) != len(set(tied))
    for index in specs:
        document_id = reference.document_id(index)
        assert_identical(precomputed._localize([], query, limit, document_id),
                         reference._localize([], query, limit, document_id))
    paths = [str(index) for index in specs]
    assert_identical(precomputed._localize(paths, query, limit, None),
                     reference._localize(paths, query, limit, None))


def test_an_article_without_a_stored_table_falls_back_to_the_built_one(tmp_path):
    """Partial coverage is the artifact's normal state mid-pass: an article whose
    shard was never written answers from the in-memory build, identically."""
    specs = {3: tie_blocks(1), 513: tie_blocks(3)}
    corpus = Corpus(tmp_path, specs, shards=[0])
    reference, precomputed = corpus.reader(False), corpus.reader(True)
    document_id = reference.document_id(513)
    assert corpus.results[0]["covered"] == 1
    assert_identical(precomputed._localize([], "filter water sand", 5, document_id),
                     reference._localize([], "filter water sand", 5, document_id))


def test_handles_that_do_not_sort_in_ordinal_order_are_not_stored(tmp_path):
    """The rowid tie-break stands on ordinal-ordered handles; an article whose
    stored spans violate that order is left to the query path rather than stored
    with a tie-break that disagrees with the one the query would apply."""
    structure = tie_blocks(1)
    passages = segment(document(), structure, profile(), Tokens(), "f" * 64)
    raw = json.loads(zlib.decompress(encode(structure, passages, lead(document(), "f" * 64, 3), None)))
    blocks, spans, stored_lead, license = raw[0], raw[1], raw[2], raw[3]
    spans[0], spans[1] = spans[1], spans[0]
    tampered = zlib.compress(json.dumps([blocks, spans, stored_lead, license],
                                        ensure_ascii=False, separators=(",", ":")).encode(), 6)
    corpus = Corpus(tmp_path, {}, payloads={3: tampered})
    assert corpus.results[0]["covered"] == 0 and corpus.results[0]["failures"] == 1
    reference, precomputed = corpus.reader(False), corpus.reader(True)
    assert_identical(precomputed._localize([], "filter water sand", 5, "z_" + "c" * 64 + "_3"),
                     reference._localize([], "filter water sand", 5, "z_" + "c" * 64 + "_3"))


def test_a_shard_bound_to_something_else_reads_as_absent(tmp_path):
    """A stale artifact must never serve tables built for another generation."""
    corpus = Corpus(tmp_path, {3: tie_blocks(1)})
    reader = corpus.reader(False)
    reader.lexicon = ArticleLexicon(corpus.directory, {**corpus.binding, "generation": "a" * 64})
    document_id = reader.document_id(3)
    assert_identical(reader._localize([], "filter water", 5, document_id),
                     corpus.reader(False)._localize([], "filter water", 5, document_id))


def test_a_damaged_shard_falls_back_and_is_counted(tmp_path):
    """A shard that cannot be read is damage to a derived artifact: the articles
    it held answer from the in-memory build, and the count says so."""
    corpus = Corpus(tmp_path, {3: tie_blocks(1)})
    shard = corpus.directory / DIRECTORY / "shard-00000.sqlite"
    shard.write_bytes(shard.read_bytes()[:2048])
    reader = corpus.reader(True)
    document_id = reader.document_id(3)
    assert_identical(reader._localize([], "filter water", 5, document_id),
                     corpus.reader(False)._localize([], "filter water", 5, document_id))
    assert reader.lexicon.undecodable > 0


def test_withdrawn_spans_bypass_the_artifact(tmp_path):
    """The tables were built from the spans; while the spans are withdrawn the
    artifact is not consulted, whatever is on disk."""
    corpus = Corpus(tmp_path, {3: tie_blocks(1)})
    reader = corpus.reader(True)
    reader.usable_spans = lambda: None
    reader.segment_article = lambda document, index: []

    def tripwire(*args, **kwargs):
        raise AssertionError("the precomputed tables were consulted while the spans were withdrawn")

    reader.lexicon.article = tripwire
    document_id = reader.document_id(3)
    assert list(reader._localize([], "filter water", 5, document_id)) == []


def test_an_empty_expression_takes_the_leading_passages(tmp_path):
    """A query with no usable terms ranks nothing; both paths answer with the
    article's first passages, in ordinal order."""
    corpus = Corpus(tmp_path, {3: tie_blocks(1)})
    document_id = corpus.reader(False).document_id(3)
    assert_identical(corpus.reader(True)._localize([], "", 5, document_id),
                     corpus.reader(False)._localize([], "", 5, document_id))


def test_the_lexical_state_cache_stays_out_of_the_artifact_path(tmp_path):
    """A covered article never enters the in-memory state cache: the artifact
    serves it, so the cache is left for the articles that need it."""
    corpus = Corpus(tmp_path, {3: tie_blocks(1)})
    reader = corpus.reader(True)
    reader._localize([], "filter water", 5, reader.document_id(3))
    assert not reader.lexical_states


def test_decoded_spans_are_reused_across_searches(tmp_path):
    """The spans decode is a search's per-article cost, paid once per reader
    lifetime: a repeated search for the same article decodes it again only
    if the cache was emptied."""
    corpus = Corpus(tmp_path, {3: tie_blocks(1)})
    reader = corpus.reader(True)
    document_id = reader.document_id(3)
    reader._localize([], "filter water", 5, document_id)
    first = reader.lexicon.decoded[3]
    assert reader.lexicon.decoded_bytes > 0
    reader._localize([], "filter water", 5, document_id)
    assert reader.lexicon.decoded[3] is first


def test_decoded_spans_are_evicted_at_the_byte_ceiling(tmp_path, monkeypatch):
    """The bound keeps the decoded footprint honest: past it, the coldest
    articles are decoded again on their next search rather than held."""
    from oracle_content import lexical
    monkeypatch.setattr(lexical, "ROWS_BYTES", 1)
    corpus = Corpus(tmp_path, {3: tie_blocks(1)})
    reader = corpus.reader(True)
    reader._localize([], "filter water", 5, reader.document_id(3))
    assert not reader.lexicon.decoded and reader.lexicon.decoded_bytes == 0
    assert list(reader._localize([], "filter water", 5, reader.document_id(3)))
    assert not reader.lexicon.decoded
