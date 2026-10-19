from types import SimpleNamespace

import threading

import pytest

from oracle_content.native import BuiltPassages, NativeReader
from oracle_content.adapters import ZimLexical


def lexical_state_reader():
    """A reader whose localization rows come from a counted stub, so reuse is observable."""
    import types
    from collections import OrderedDict
    reader = NativeReader.__new__(NativeReader)
    reader.profile = types.SimpleNamespace(rrf_k=60.0)
    reader.template = types.SimpleNamespace(sha256="a" * 64)
    reader.lexical_states = OrderedDict()
    reader.lexical_state_bytes = 0
    reader.cache_lock = threading.RLock()
    reader.spans = object()
    reader.usable_spans = lambda: reader.spans
    reader.calls = []
    rows = [("p:" + "b" * 64 + ":0001", "pressure regulator valve"),
            ("p:" + "b" * 64 + ":0002", "regulator")]
    article = types.SimpleNamespace(rows=rows)
    reader.localizable = lambda document_id: (reader.calls.append(document_id), article)[1]
    return reader, article


def test_lexical_state_reuses_the_built_table_across_searches():
    """The FTS5 table an article is localized with is built once per reader and
    reused, or a repeated search re-pays the decode and insert for every article
    it touches."""
    reader, article = lexical_state_reader()
    first, first_db = reader.lexical_state("z" + "a" * 63 + "_7")
    assert first is article and len(reader.calls) == 1
    assert {row[0] for row in first_db.execute("SELECT id FROM article WHERE article MATCH 'regulator'").fetchall()} \
        == {"p:" + "b" * 64 + ":0001", "p:" + "b" * 64 + ":0002"}
    second, second_db = reader.lexical_state("z" + "a" * 63 + "_7")
    assert second is article and second_db is first_db and len(reader.calls) == 1
    assert reader.lexical_state_bytes > 0


def test_lexical_state_is_dropped_when_the_spans_are_withdrawn():
    """A withdrawn spans artifact must never be served from the cache, so the
    cache is emptied whole and the answer rebuilt."""
    reader, article = lexical_state_reader()
    reader.lexical_state("z" + "a" * 63 + "_7")
    reader.spans = None
    rebuilt, db = reader.lexical_state("z" + "a" * 63 + "_7")
    assert rebuilt is article and db is None and len(reader.calls) == 2
    assert not reader.lexical_states and reader.lexical_state_bytes == 0


@pytest.mark.parametrize("counts", [[40] * 40, [1] * 40, [0, 2, 19, 1, 0, 40] * 7])
@pytest.mark.parametrize("constant", [1.0, 60.0, 200.0])
def test_lazy_native_localization_matches_exhaustive_ranking(counts, constant):
    reader = NativeReader.__new__(NativeReader)
    reader.profile = SimpleNamespace(rrf_k=constant)
    reader.template = SimpleNamespace(sha256="a" * 64)
    reader.archive = SimpleNamespace(get_entry_by_path=lambda path: SimpleNamespace(is_redirect=False, _index=int(path)))
    reader.document = lambda document_id: SimpleNamespace(document_id=document_id)
    records = {}
    exhaustive = []
    for index, count in enumerate(counts):
        rows = [SimpleNamespace(passage_id=f"p:{'b' * 64}:{index:032x}{ordinal:032x}", lexical_text="pressure regulator")
                for ordinal in range(count)]
        records[reader.document_id(index)] = rows
        for ordinal, row in enumerate(rows, 1):
            exhaustive.append((row.passage_id, 1 / ((constant + index + 1) * (constant + ordinal))))
    visited = []
    def passages(document_id):
        visited.append(document_id)
        return records[document_id]
    reader.lexical_state = lambda document_id: (BuiltPassages(passages(document_id)), None)
    actual = reader._localize([str(index) for index in range(len(counts))], "pressure", 40, None)
    expected = sorted(exhaustive, key=lambda row: (-row[1], row[0]))[:40]
    assert list(actual) == expected
    assert set(actual.passages) == {pid for pid, _ in expected}
    if counts == [40] * 40:
        assert len(visited) < 15
    if counts == [1] * 40:
        assert len(visited) == 40


@pytest.mark.parametrize("query", ["Water", "water"])
def test_exact_title_is_discoverable_when_fulltext_buries_article(query):
    import asyncio
    reader = NativeReader.__new__(NativeReader)
    reader.path = "archive.zim"
    reader.verify_original = lambda: None
    def by_title(title):
        if title != "Water":
            raise KeyError(title)
        return SimpleNamespace(path="Water", get_item=lambda: SimpleNamespace(path="Water"))
    reader.archive = SimpleNamespace(get_entry_by_title=by_title)
    reader._localize = lambda paths, *args: paths
    class Search:
        async def search(self, path, safe, limit, *, title_query):
            assert title_query == query
            return ZimLexical._with_exact_title(reader.archive, title_query,
                ["Water_companies", "Water_politics", "Water_tower"], limit)
    assert asyncio.run(reader.lexical(Search(), query, 3)) == [
        "Water", "Water_companies", "Water_politics",
    ]


def test_exact_title_merge_preserves_depth_and_deduplicates():
    archive = SimpleNamespace(get_entry_by_title=lambda title: SimpleNamespace(
        path="Water", get_item=lambda: SimpleNamespace(path="Water")))
    assert ZimLexical._with_exact_title(archive, "Water", ["Other", "Water", "Third"], 3) == ["Water", "Other", "Third"]


def test_exact_redirect_title_deduplicates_the_canonical_article_before_depth_limit():
    archive = SimpleNamespace(get_entry_by_title=lambda title: SimpleNamespace(
        path="Stopcock", get_item=lambda: SimpleNamespace(path="Valve")))
    assert ZimLexical._with_exact_title(archive, "Stopcock", ["Valve", "Pressure"], 2) == [
        "Valve", "Pressure",
    ]


def test_native_localization_does_not_spend_passage_depth_on_redirect_duplicates():
    reader = NativeReader.__new__(NativeReader)
    reader.profile = SimpleNamespace(rrf_k=60)
    reader.template = SimpleNamespace(sha256="a" * 64)
    target = SimpleNamespace(is_redirect=False, _index=0)
    entries = {"Stopcock": SimpleNamespace(is_redirect=True, get_redirect_entry=lambda: target),
               "Valve": target, "Pressure": SimpleNamespace(is_redirect=False, _index=1)}
    reader.archive = SimpleNamespace(get_entry_by_path=entries.__getitem__)
    reader.document = lambda document_id: SimpleNamespace(document_id=document_id)
    visited = []
    def passages(document_id):
        visited.append(document_id)
        return [SimpleNamespace(passage_id=document_id, lexical_text="valve pressure")]
    reader.lexical_state = lambda document_id: (BuiltPassages(passages(document_id)), None)

    rows = reader._localize(["Stopcock", "Valve", "Pressure"], "valve", 2, None)

    assert [pid for pid, _score in rows] == [reader.document_id(0), reader.document_id(1)]
    assert visited == [reader.document_id(0), reader.document_id(1)]


@pytest.mark.parametrize('base,path,expected', [
    ('https://www.example.org', 'www.example.org/manual/Water.html', 'https://www.example.org/manual/Water.html'),
    ('https://en.wikipedia.org/wiki', 'Water', 'https://en.wikipedia.org/wiki/Water'),
])
def test_native_source_url_handles_host_qualified_archive_paths(base, path, expected):
    reader = NativeReader.__new__(NativeReader)
    reader.template = SimpleNamespace(sha256='a'*64, source_url=base, license='source notices', edition='', original_path='archive', model_copy=lambda update: update)
    reader.archive_edition = ''
    reader.rights_exclusions = {}
    reader.policy = 'canonical-html'
    reader.entry = lambda index: SimpleNamespace(path=path, title='Water')
    assert reader._document(reader.document_id(1))['source_url'] == expected
