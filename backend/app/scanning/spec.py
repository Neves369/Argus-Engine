from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FormField:
    name: str
    type: str
    value: str | None = None


@dataclass
class HtmlForm:
    action: str
    method: str
    fields: list[FormField] = field(default_factory=list)


@dataclass
class TargetPage:
    """A single page observed from the target (evidence-grounded scan result).

    Mirrors exactly what was received — status code, headers, body, and the
    parsed structural signals — and is serializable so a run can persist the
    raw scan for the audit/report (see ``GraphState.scan``).
    """

    url: str
    status_code: int
    headers: dict[str, str]
    body: str
    body_truncated: bool = False
    final_url: str | None = None
    links: list[str] = field(default_factory=list)
    forms: list[HtmlForm] = field(default_factory=list)
    tech: list[str] = field(default_factory=list)

    @property
    def host(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.url).netloc

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "headers": dict(self.headers),
            "body": self.body,
            "body_truncated": self.body_truncated,
            "final_url": self.final_url,
            "links": list(self.links),
            "forms": [
                {
                    "action": f.action,
                    "method": f.method,
                    "fields": [
                        {"name": fld.name, "type": fld.type, "value": fld.value}
                        for fld in f.fields
                    ],
                }
                for f in self.forms
            ],
            "tech": list(self.tech),
        }