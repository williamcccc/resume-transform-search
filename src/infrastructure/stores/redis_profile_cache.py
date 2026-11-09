"""
ICandidateProfileCache 之 Redis 實作 (ADR-0019)

鍵：{profile_prefix}{extractor_version}:{candidate_id} -> JSON {content_hash, profile, created_at}
    {jd_prefix}{extractor_version}:{jd_hash}          -> JSON {jd, created_at}
讀取時比對 content_hash，不符視為未命中（AC-14）；Redis 故障記 WARNING 並視為未命中，不阻斷對話。
"""
import json
import logging
import time
from typing import Any, Callable, Optional

from src.domain.recruitment import CandidateProfile, JdRequirements
from src.domain.recruitment_codec import jd_from_dict, jd_to_dict, profile_from_dict, profile_to_dict

logger = logging.getLogger(__name__)


class RedisProfileCache:
    def __init__(
        self,
        redis_client: Any,
        profile_prefix: str,
        jd_prefix: str,
        ttl_seconds: int,
        clock: Callable[[], float] = time.time,
    ):
        self._client = redis_client
        self._profile_prefix = profile_prefix
        self._jd_prefix = jd_prefix
        self._ttl = max(int(ttl_seconds), 1)
        self._clock = clock

    @classmethod
    def from_url(cls, redis_url: str, profile_prefix: str, jd_prefix: str, ttl_seconds: int) -> "RedisProfileCache":
        import redis

        client = redis.Redis.from_url(redis_url, decode_responses=True)
        return cls(client, profile_prefix, jd_prefix, ttl_seconds)

    def profile_key(self, candidate_id: str, extractor_version: str) -> str:
        return f"{self._profile_prefix}{extractor_version}:{candidate_id}"

    def jd_key(self, jd_hash: str, extractor_version: str) -> str:
        return f"{self._jd_prefix}{extractor_version}:{jd_hash}"

    def get_profile(self, candidate_id: str, content_hash: str, extractor_version: str) -> Optional[CandidateProfile]:
        payload = self._read(self.profile_key(candidate_id, extractor_version))
        if not payload or payload.get("content_hash") != content_hash:
            return None
        try:
            return profile_from_dict(payload["profile"])
        except (KeyError, TypeError, ValueError) as err:
            logger.warning("Profile 快取內容損毀，視為未命中 (err_type=%s)", type(err).__name__)
            return None

    def set_profile(self, profile: CandidateProfile) -> None:
        payload = {
            "content_hash": profile.content_hash,
            "profile": profile_to_dict(profile),
            "created_at": self._clock(),
        }
        self._write(self.profile_key(profile.candidate_id, profile.extractor_version), payload)

    def get_jd(self, jd_hash: str, extractor_version: str) -> Optional[JdRequirements]:
        payload = self._read(self.jd_key(jd_hash, extractor_version))
        if not payload:
            return None
        try:
            return jd_from_dict(payload["jd"])
        except (KeyError, TypeError, ValueError) as err:
            logger.warning("JD 快取內容損毀，視為未命中 (err_type=%s)", type(err).__name__)
            return None

    def set_jd(self, jd: JdRequirements, extractor_version: str) -> None:
        self._write(self.jd_key(jd.jd_hash, extractor_version), {"jd": jd_to_dict(jd), "created_at": self._clock()})

    def close(self) -> None:
        try:
            self._client.close()
        except Exception as err:
            logger.warning("Profile 快取連線關閉異常 (err_type=%s)", type(err).__name__)

    def _read(self, key: str) -> Optional[dict]:
        try:
            raw = self._client.get(key)
        except Exception as err:
            logger.warning("Profile 快取讀取失敗，視為未命中 (err_type=%s)", type(err).__name__)
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as err:
            logger.warning("Profile 快取 JSON 解析失敗，視為未命中 (err_type=%s)", type(err).__name__)
            return None
        return data if isinstance(data, dict) else None

    def _write(self, key: str, payload: dict) -> None:
        try:
            self._client.set(key, json.dumps(payload, ensure_ascii=False), ex=self._ttl)
        except Exception as err:
            logger.warning("Profile 快取寫入失敗 (err_type=%s)", type(err).__name__)
