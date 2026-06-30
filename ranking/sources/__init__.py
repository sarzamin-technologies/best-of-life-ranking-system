"""Data-source clients. Each module degrades gracefully when its key is absent:
the top-level `enabled()` returns False and the fetch functions return empty
results, so the pipeline runs on whatever sources are configured.
"""
