"""Кэш-Redis (docs/plans/redis_split.md, шаг а): без CACHE_REDIS_URL — тот же
REDIS_URL, на проде ничего не меняется; с ним — туда идут только
пересчитываемые кэши, платные тексты остаются в основном."""
from backend import cache
from backend.cache import redis_url

MAIN, CACHE = "redis://:p@redis:6379/0", "redis://:p@redis-cache:6379/0"


def test_without_cache_url_same_redis(monkeypatch):
    monkeypatch.setenv("REDIS_URL", MAIN)
    monkeypatch.delenv("CACHE_REDIS_URL", raising=False)
    assert redis_url(True) == redis_url(False) == MAIN


def test_with_cache_url_only_cache_moves(monkeypatch):
    monkeypatch.setenv("REDIS_URL", MAIN)
    monkeypatch.setenv("CACHE_REDIS_URL", CACHE)
    assert redis_url(True) == CACHE
    assert redis_url(False) == MAIN


def test_which_prefixes_are_cache():
    from backend.ephemeris.geo import _geo_cache
    from backend.feed.builder import feed_cache
    from backend.sky import sky_cache
    for c in (sky_cache, feed_cache, cache.transit_cache, cache.chat_transits_cache, _geo_cache):
        assert c._cache, c._prefix
    # Платные тексты — не в вытесняемом кэше.
    for c in (cache.interpretation_cache, cache.transit_interp_cache):
        assert not c._cache, c._prefix
