from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _Rule:
    path: str
    allow: bool


class RobotsRules:
    """Robots.txt rules for a single host (self-imposed restriction).

    Applies the classic semantics: a ``Disallow`` (or ``Allow``) prefix match
    on the request path for the group that mentions our user agent, falling
    back to the ``*`` group. A path is allowed unless a Disallow prefix
    matches and no more specific Allow prefix wins.
    """

    def __init__(self) -> None:
        self._rules: list[_Rule] = []

    @classmethod
    def parse(cls, text: str, *, user_agent: str) -> RobotsRules:
        rules = cls()
        group_agent: str | None = None
        group_rules: list[_Rule] = []
        ua = user_agent.lower()

        def flush() -> None:
            if group_agent is not None and (group_agent == "*" or group_agent in ua):
                rules._rules.extend(group_rules)

        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "user-agent":
                flush()
                group_agent = value.lower()
                group_rules = []
            elif key in ("allow", "disallow") and group_agent is not None:
                if not value:
                    value = "/"
                group_rules.append(_Rule(path=value, allow=(key == "allow")))
        flush()
        return rules

    def is_allowed(self, path: str) -> bool:
        if not self._rules:
            return True
        path = path or "/"
        matches = [r for r in self._rules if path.startswith(r.path)]
        if not matches:
            return True
        winner = max(matches, key=lambda r: len(r.path))
        return winner.allow

    @classmethod
    def allow_all(cls) -> RobotsRules:
        return cls()