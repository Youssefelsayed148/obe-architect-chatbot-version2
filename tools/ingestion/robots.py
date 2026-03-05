from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Rule:
    directive: str
    value: str


class RobotsPolicy:
    def __init__(self, rules: list[Rule], sitemaps: list[str] | None = None) -> None:
        self.rules = rules
        self.sitemaps = sitemaps or []

    def can_fetch(self, url_or_path: str) -> bool:
        parsed = urlparse(url_or_path)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"

        matched: Rule | None = None
        for rule in self.rules:
            if target.startswith(rule.value):
                if matched is None or len(rule.value) > len(matched.value):
                    matched = rule
        if matched is None:
            return True
        return matched.directive == "allow"


def parse_robots_txt(content: str, user_agent: str = "*") -> RobotsPolicy:
    lines = [line.strip() for line in content.splitlines()]
    current_agents: list[str] = []
    matched_rules: list[Rule] = []
    sitemaps: list[str] = []
    target_agent = user_agent.strip().lower()

    for line in lines:
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "sitemap":
            sitemaps.append(value)
            continue
        if key == "user-agent":
            current_agents = [value.lower()]
            continue
        if key not in {"allow", "disallow"}:
            continue
        if not value:
            continue
        applies = "*" in current_agents or target_agent in current_agents
        if applies:
            matched_rules.append(Rule(key, value))

    return RobotsPolicy(matched_rules, sitemaps=sitemaps)
