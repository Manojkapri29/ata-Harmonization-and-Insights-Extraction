"""Pluggable job-source architecture.

A source is a class with a `key`, some metadata, and `search(query) -> list[RawJob]`.
Register it with @register and it shows up in the API, the Settings page and search profiles.

Every HTTP call goes through PoliteClient, which:
  * identifies itself with a clear User-Agent,
  * checks robots.txt before fetching pages (official JSON APIs are exempt only when documented as public APIs),
  * waits between requests to the same domain,
  * never sends cookies or credentials for job boards.
"""
from __future__ import annotations

import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from ...config import get_settings
from ..normalize import RawJob


class SourceError(Exception):
    """A source could not run (missing credentials, blocked by robots.txt, site error)."""


class RobotsDisallowed(SourceError):
    pass


@dataclass
class SearchQuery:
    keywords: list[str]
    locations: list[str] = field(default_factory=list)
    include_remote: bool = True
    posted_within_days: int = 7
    experience_min: float | None = None
    experience_max: float | None = None
    min_salary_monthly: int | None = None
    max_results: int = 100
    options: dict = field(default_factory=dict)   # per-source config (company board names, feed URLs, ...)

    @property
    def text(self) -> str:
        return " ".join(self.keywords)


class PoliteClient:
    _lock = threading.Lock()
    _last_hit: dict[str, float] = {}
    _robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def __init__(self):
        s = get_settings()
        self.ua = s.http_user_agent
        self.delay = s.min_seconds_between_requests_per_domain
        self.client = httpx.Client(timeout=s.http_timeout_seconds, follow_redirects=True,
                                   headers={"User-Agent": self.ua, "Accept-Language": "en-IN,en;q=0.9"})

    def _wait_turn(self, host: str) -> None:
        with self._lock:
            wait = self._last_hit.get(host, 0) + self.delay - time.monotonic()
            self._last_hit[host] = time.monotonic() + max(wait, 0)
        if wait > 0:
            time.sleep(wait)

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(f"{root}/robots.txt")
                if r.status_code >= 400:
                    rp = None                      # no robots.txt -> allowed
                else:
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp = None
            self._robots[root] = rp
        rp = self._robots[root]
        return True if rp is None else rp.can_fetch(self.ua, url)

    def get(self, url: str, *, params: dict | None = None, check_robots: bool = True) -> httpx.Response:
        if check_robots and not self.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows fetching {url}. Import this job manually instead.")
        self._wait_turn(urlparse(url).netloc)
        r = self.client.get(url, params=params)
        if r.status_code in (401, 403, 429):
            raise SourceError(f"{urlparse(url).netloc} refused the request (HTTP {r.status_code}). "
                              "It may need login or be rate-limiting; use manual/URL import.")
        r.raise_for_status()
        return r

    def json(self, url: str, *, params: dict | None = None, check_robots: bool = False):
        # Documented public JSON APIs are meant for programmatic access, so robots.txt (written for crawlers
        # of HTML pages) is not consulted for them by default.
        return self.get(url, params=params, check_robots=check_robots).json()

    def close(self) -> None:
        self.client.close()


class SourceAdapter:
    key: str = ""
    name: str = ""
    kind: str = "api"                 # api | feed | company | assisted | demo
    description: str = ""
    requires_credentials: list[str] = []   # env var names
    config_fields: list[dict] = []          # [{"name": "companies", "label": "...", "placeholder": "..."}]
    default_enabled: bool = True
    supports_search: bool = True            # False = assisted/manual (browser links + import only)
    server_side_filtering: bool = False     # True when the API already filters by keyword/location
    terms_note: str = ""

    def search(self, query: SearchQuery, http: PoliteClient) -> list[RawJob]:  # pragma: no cover - interface
        raise NotImplementedError

    def search_links(self, query: SearchQuery) -> list[dict]:
        """Browser links the user can open themselves (assisted sources)."""
        return []

    def missing_credentials(self) -> list[str]:
        s = get_settings()
        return [c for c in self.requires_credentials if not getattr(s, c.lower(), "")]

    def meta(self) -> dict:
        return {"key": self.key, "name": self.name, "kind": self.kind, "description": self.description,
                "requires_credentials": self.requires_credentials, "missing_credentials": self.missing_credentials(),
                "config_fields": self.config_fields, "supports_search": self.supports_search,
                "default_enabled": self.default_enabled, "terms_note": self.terms_note}


REGISTRY: dict[str, SourceAdapter] = {}


def register(cls: type[SourceAdapter]) -> type[SourceAdapter]:
    REGISTRY[cls.key] = cls()
    return cls
