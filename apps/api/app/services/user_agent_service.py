"""Lightweight server-side user-agent parsing.

Pure regex heuristics so we don't add a dependency. Not perfect, but good
enough for dashboard bucketing (Chrome vs Edge vs Safari, Windows vs macOS
vs Linux, desktop vs mobile). If a UA cannot be parsed, all fields return
None and the dashboard shows "unknown" bucket.
"""
from __future__ import annotations

import re
from typing import Optional, TypedDict


class UserAgentInfo(TypedDict, total=False):
    browser_name: Optional[str]
    browser_version: Optional[str]
    os_name: Optional[str]
    os_version: Optional[str]
    device_type: Optional[str]


_BROWSERS: list[tuple[str, re.Pattern[str]]] = [
    ("Edge", re.compile(r"Edg[eA]?/([\d.]+)")),
    ("Chrome", re.compile(r"Chrome/([\d.]+)")),
    ("Firefox", re.compile(r"Firefox/([\d.]+)")),
    ("Safari", re.compile(r"Version/([\d.]+).*Safari/")),
    ("Opera", re.compile(r"OPR/([\d.]+)")),
    ("IE", re.compile(r"MSIE ([\d.]+)|Trident/.*rv:([\d.]+)")),
]

_OS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Windows", re.compile(r"Windows NT ([\d.]+)")),
    ("macOS", re.compile(r"Mac OS X ([\d_\.]+)")),
    ("iOS", re.compile(r"iPhone OS ([\d_\.]+)|iPad; CPU OS ([\d_\.]+)")),
    ("Android", re.compile(r"Android ([\d.]+)")),
    ("ChromeOS", re.compile(r"CrOS")),
    ("Linux", re.compile(r"Linux")),
]


def parse_user_agent(ua: str | None) -> UserAgentInfo:
    if not ua:
        return {
            "browser_name": None,
            "browser_version": None,
            "os_name": None,
            "os_version": None,
            "device_type": None,
        }

    info: UserAgentInfo = {
        "browser_name": None,
        "browser_version": None,
        "os_name": None,
        "os_version": None,
        "device_type": "desktop",
    }

    for name, pat in _BROWSERS:
        m = pat.search(ua)
        if m:
            info["browser_name"] = name
            version = next((g for g in m.groups() if g), None)
            info["browser_version"] = version
            break

    for name, pat in _OS_PATTERNS:
        m = pat.search(ua)
        if m:
            info["os_name"] = name
            version = next((g for g in m.groups() if g), None)
            if version:
                info["os_version"] = version.replace("_", ".")
            break

    lowered = ua.lower()
    if "mobile" in lowered or "iphone" in lowered or "android" in lowered:
        if "tablet" in lowered or "ipad" in lowered:
            info["device_type"] = "tablet"
        else:
            info["device_type"] = "mobile"
    elif "ipad" in lowered or "tablet" in lowered:
        info["device_type"] = "tablet"

    return info
