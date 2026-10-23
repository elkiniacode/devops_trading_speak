"""Remove secrets and personal paths before anything is stored or served."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path, PureWindowsPath

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
SECRETS = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "sk-[redacted]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "gh_[redacted]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*"), "Bearer [redacted]"),
    # Env-style assignments such as OPENROUTER_API_KEY=value.
    (re.compile(r"\b((?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*)=([^\s\"'`]+)"), r"\1=[redacted]"),
]


@lru_cache(maxsize=1)
def account_names() -> tuple[str, ...]:
    """The local Claude account's email name, read from ~/.claude.json so it is masked even without the @domain."""
    try:
        config = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
        email = (config.get("oauthAccount") or {}).get("emailAddress") or ""
    except (OSError, ValueError, AttributeError):
        return ()
    local = email.split("@")[0]
    return (local,) if len(local) >= 5 else ()


class Redactor:
    """Masks emails and key-like strings, shortens the home folder to ~, and makes paths project-relative."""

    def __init__(self, home: str | Path | None = None, project: str | None = None, names: tuple[str, ...] | None = None):
        home = str(home or Path.home())
        variants = {home, home.replace("\\", "/"), home.replace("\\", "\\\\")}
        win = PureWindowsPath(home)
        if win.drive:
            rest = "/".join(win.parts[1:])
            drive = win.drive[0].lower()
            variants |= {f"/{drive}/{rest}", f"/mnt/{drive}/{rest}"}
        pattern = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
        self._home = re.compile(pattern, re.IGNORECASE)
        user = re.escape(PureWindowsPath(home).name if win.drive else Path(home).name)
        # Leftover fragments such as "Users/<user>" or "home/<user>" that aren't a full home path.
        # No leading \b: in escaped text the fragment can follow a literal "\n".
        self._user_dir = re.compile(rf"(Users|home)([\\/]+){user}\b", re.IGNORECASE) if user else None
        names = account_names() if names is None else names
        self._names = re.compile("|".join(re.escape(n) for n in names), re.IGNORECASE) if names else None
        self._project = project.replace("\\", "/").rstrip("/") if project else None

    def text(self, value: str | None) -> str | None:
        if not value:
            return value
        value = EMAIL.sub("[email]", value)
        for pattern, replacement in SECRETS:
            value = pattern.sub(replacement, value)
        value = self._home.sub("~", value)
        if self._user_dir:
            value = self._user_dir.sub(r"\1\2[user]", value)
        if self._names:
            value = self._names.sub("[email]", value)
        return value

    def path(self, value: str | None, cwd: str | None = None) -> str | None:
        """A display path: relative to the project when inside it, else with the home folder as ~."""
        if not value:
            return value
        absolute = re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("/", "\\\\"))
        if not absolute and cwd:
            value = cwd.rstrip("\\/") + "/" + value
        norm = value.replace("\\", "/")
        if self._project and norm.lower().startswith(self._project.lower() + "/"):
            return norm[len(self._project) + 1 :]
        return self.text(norm)
