"""Precompute per-article FTS5 lexical tables so a first touch stops building them."""
import argparse
import json
import signal
from pathlib import Path

from oracle_content.lexical import build_lexical
from oracle_content.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--generation", action="append", default=[],
                        help="Repeatable; defaults to every active native generation")
    parser.add_argument("--workers", type=int, default=1, help="Bounded shard-building workers")
    parser.add_argument("--min-free-bytes", type=int, default=8 * 1024 ** 3,
                        help="Stop and publish rather than take the filesystem below this")
    parser.add_argument("--stop-after-shards", type=int,
                        help="Build at most this many not-yet-published shards, for a measured pilot")
    args = parser.parse_args()
    if not 1 <= args.workers <= 64:
        raise SystemExit("workers must be between 1 and 64")

    def interrupted(number, frame):
        """Without this a SIGTERM ends the process before the build can publish
        what it has, throwing away completed shards."""
        raise KeyboardInterrupt(f"signal {number}")

    signal.signal(signal.SIGTERM, interrupted)

    store = Store(args.data)
    generations = args.generation or [value for value in store.active_generations()
                                      if store.manifest(value).get("kind") == "native-zim-article-v1"]
    results = {}
    for generation in generations:
        print("=== " + generation, flush=True)
        results[generation] = build_lexical(store, generation, workers=args.workers,
                                           min_free_bytes=args.min_free_bytes,
                                           stop_after_shards=args.stop_after_shards,
                                           log=lambda line: print(line, flush=True))
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
