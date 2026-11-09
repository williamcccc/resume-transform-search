"""
RedisProfileCache 單元測試 (MagicMock Redis)：鍵格式、TTL、Hash 不符未命中、Redis 例外降級為未命中。
"""
import json
import unittest
from unittest.mock import MagicMock

from src.domain.recruitment import CandidateProfile, EvidenceQuote
from src.domain.recruitment_services import renumber_requirements
from src.infrastructure.stores.redis_profile_cache import RedisProfileCache
from tests.unit.recruitment_fakes import make_jd


def profile(content_hash="h1"):
    return CandidateProfile("cand_a", content_hash, "ver1", 8.0, True, 6, None, ("python",),
                            (EvidenceQuote("years", "8年工作經驗", True),))


class DictRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttls[key] = ex


class TestRedisProfileCache(unittest.TestCase):
    def setUp(self):
        self.redis = DictRedis()
        self.cache = RedisProfileCache(self.redis, "recruit:v1:profile:", "recruit:v1:jd:", 3600, clock=lambda: 1.0)

    def test_set_and_get_profile_should_use_versioned_key_and_ttl(self):
        self.cache.set_profile(profile())
        key = "recruit:v1:profile:ver1:cand_a"
        self.assertIn(key, self.redis.store)
        self.assertEqual(self.redis.ttls[key], 3600)
        self.assertEqual(json.loads(self.redis.store[key])["content_hash"], "h1")
        self.assertEqual(self.cache.get_profile("cand_a", "h1", "ver1"), profile())

    def test_hash_or_version_mismatch_should_miss(self):
        self.cache.set_profile(profile())
        self.assertIsNone(self.cache.get_profile("cand_a", "h2", "ver1"))
        self.assertIsNone(self.cache.get_profile("cand_a", "h1", "ver2"))

    def test_jd_round_trip(self):
        jd, _ = renumber_requirements(make_jd(), 12)
        jd = type(jd)("jdhash", jd.title, jd.must, jd.nice, jd.retrieval_query)
        self.cache.set_jd(jd, "ver1")
        self.assertIn("recruit:v1:jd:ver1:jdhash", self.redis.store)
        self.assertEqual(self.cache.get_jd("jdhash", "ver1"), jd)
        self.assertIsNone(self.cache.get_jd("other", "ver1"))

    def test_redis_errors_should_degrade_to_miss(self):
        broken = MagicMock()
        broken.get.side_effect = ConnectionError("down")
        broken.set.side_effect = ConnectionError("down")
        cache = RedisProfileCache(broken, "p:", "j:", 10)
        with self.assertLogs("src.infrastructure.stores.redis_profile_cache", level="WARNING"):
            self.assertIsNone(cache.get_profile("c", "h", "v"))
            cache.set_profile(profile())

    def test_corrupted_payload_should_miss(self):
        self.redis.store["recruit:v1:profile:ver1:cand_a"] = "{not json"
        self.assertIsNone(self.cache.get_profile("cand_a", "h1", "ver1"))
        self.redis.store["recruit:v1:profile:ver1:cand_a"] = json.dumps({"content_hash": "h1", "profile": {}})
        self.assertIsNone(self.cache.get_profile("cand_a", "h1", "ver1"))


if __name__ == "__main__":
    unittest.main()
