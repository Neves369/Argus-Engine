from __future__ import annotations

import enum
import ipaddress
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceKind(enum.StrEnum):
    HTTP = "http"
    CVE = "cve"


def looks_like_ip(value: str) -> bool:
    """True if `value` parses as an IPv4/IPv6 address (vs. a hostname/domain)."""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


class DataSourceSpec(BaseModel):
    """Declarative description of an external data source provided by the operator.

    Sources are read-only information channels (CVE, OSINT, ...). Only the fields
    listed in ``fields`` are kept when normalizing a response (data minimization).
    """

    name: str
    description: str = ""
    kind: SourceKind = SourceKind.HTTP
    url: str | None = None
    method: str = "GET"
    params_template: dict[str, Any] = Field(default_factory=dict)
    #: Static request headers, merged into every call. A value of the exact
    #: form ``"${ENV_VAR}"`` is resolved from the process environment at
    #: request time (never stored as a literal secret in the manifest); if
    #: the variable is unset, that header is simply omitted rather than sent
    #: as the literal placeholder string.
    headers_template: dict[str, str] = Field(default_factory=dict)
    timeout: float = 10.0
    rate_limit: float = 0.0
    #: Token-bucket burst capacity for ``rate_limit``: how many calls may be
    #: served back-to-back before the refill rate (``rate_limit`` per second)
    #: governs. Default 1 preserves strict one-call-per-window behavior; a
    #: single run may need e.g. the sweep *and* the CVE correlation to query
    #: NVD within seconds — burst 5 mirrors NVD's anonymous 5 req/30s budget.
    rate_burst: int = 1
    ttl: int = 3600
    fields: list[str] = Field(default_factory=list)
    #: Name of the parameter the collector's generic query value is placed
    #: under when calling this source (e.g. ``"ipAddress"`` for AbuseIPDB,
    #: ``"keywordSearch"`` for NVD). Also matches a ``{name}`` placeholder in
    #: ``url`` for path-style APIs (e.g. ``http://ip-api.com/json/{query}``).
    query_param: str = "q"
    #: When true, the generic per-run sweep (``BaseArchetype._collect_sources``)
    #: never calls this source automatically. Used for sources that are only
    #: meaningful via a targeted lookup (e.g. the CISA KEV catalog, queried by
    #: the CVE-correlation service with its own CVE IDs) — keeps a full-feed
    #: download out of every run's sweep.
    skip_sweep: bool = False
    #: What kind of target this source is meaningful for. The generic,
    #: per-run OSINT sweep (``BaseArchetype._collect_sources``) only calls a
    #: source automatically when the run's target matches: "domain" sources
    #: skip IP targets and vice versa; "cve" sources are never called by the
    #: generic sweep (they need an actual CVE ID, supplied via a direct
    #: `POST /sources/{name}/query` call instead); "any" always matches.
    target_kind: Literal["any", "domain", "ip", "cve"] = "any"
