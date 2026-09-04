"""Adapter around the gog CLI.

The only module in this package that touches a subprocess. Everything it
returns is plain data, so the rest of the sync is testable without Google.

gog emits raw Google Calendar API resources as JSON, plus a `calendarId`
field on each event when listing across calendars. That is the same shape
the old gws adapter returned, so normalization is untouched.
"""

import json
import os
import re
import subprocess

MINIMUM_VERSION = (0, 30, 0)
FALLBACK_COLOR = "#9e9e9e"
MAX_RESULTS = 250

_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


class GogError(Exception):
    """Base class for every failure this adapter reports."""


class GogMissing(GogError):
    """The gog binary is not on PATH."""


class GogTooOld(GogError):
    """The installed gog predates the flags this sync relies on."""


class GogAuthError(GogError):
    """Credentials are absent, expired, or lack the calendar scope."""


class GogApiError(GogError):
    """Google returned an error, or gog returned something unparseable."""


def _subprocess_runner(argv, env):
    completed = subprocess.run(argv, env=env, capture_output=True, text=True)
    return completed.returncode, completed.stdout, completed.stderr


class Gog:
    def __init__(self, account=None, runner=None, binary="gog"):
        self.account = account
        self.binary = str(binary or "gog")
        self._runner = runner or _subprocess_runner

    def _base(self):
        # --no-input: never prompt (the timer has no terminal to answer on).
        # --readonly: block mutating API requests at runtime. Belt and braces
        # next to the read-only OAuth scope from sync/setup.
        args = ["--no-input", "--readonly"]
        if self.account:
            args += ["--account", self.account]
        return args

    def _run(self, args):
        argv = [self.binary, *self._base(), *args]
        try:
            code, stdout, stderr = self._runner(argv, dict(os.environ))
        except FileNotFoundError as error:
            raise GogMissing(
                f"{self.binary} is not installed or not on PATH. "
                "Install it (go install github.com/openclaw/gogcli/cmd/gog@latest), "
                "then run sync/setup. A systemd user service does not inherit "
                "your shell PATH, so set gogPath to an absolute path in "
                "calendar-sync.json."
            ) from error
        return code, stdout, stderr

    def version(self):
        _, stdout, _ = self._run(["--version"])
        match = _VERSION.search(stdout)
        if not match:
            raise GogApiError(f"cannot parse gog version from {stdout!r}")
        return tuple(int(part) for part in match.groups())

    def check(self):
        found = self.version()
        if found < MINIMUM_VERSION:
            wanted = ".".join(str(p) for p in MINIMUM_VERSION)
            have = ".".join(str(p) for p in found)
            raise GogTooOld(f"gog {wanted} or newer is required, found {have}")

    def calendars(self):
        payload = self._json(["calendar", "calendars", "--all", "--json"])
        calendars = [
            {
                "id": item["id"],
                "name": item.get("summary") or item["id"],
                "color": item.get("backgroundColor") or FALLBACK_COLOR,
            }
            for item in payload.get("calendars", [])
        ]
        return sorted(calendars, key=lambda calendar: calendar["name"])

    def events(self, time_min, time_max):
        """Every event on every calendar in the window, in one call.

        Each item carries its own `calendarId`, so callers group rather than
        query per calendar. Extra gog-computed keys (startLocal, timezone,
        ...) are ignored downstream.
        """
        payload = self._json(
            [
                "calendar", "events", "--all",
                "--from", time_min,
                "--to", time_max,
                "--max", str(MAX_RESULTS),
                "--all-pages",
                "--sort", "start",
                "--json",
            ]
        )
        return payload.get("events", [])

    def _json(self, args):
        """Run gog and parse stdout.

        Prompts, progress, and warnings go to stderr by gog's own contract,
        so stderr is never parsed as data. On a nonzero exit, stderr is
        quoted in the raised error instead.
        """
        exit_code, stdout, stderr = self._run(args)

        if exit_code != 0:
            excerpt = stderr.strip().splitlines()
            excerpt = excerpt[-1][:300] if excerpt else "no stderr output"
            # gog exit codes: 4 = auth required, 6 = permission denied.
            if exit_code in (4, 6):
                raise GogAuthError(f"gog: {excerpt}")
            raise GogApiError(f"gog exited with code {exit_code}: {excerpt}")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise GogApiError(f"gog returned unparseable output: {error}") from error

        if isinstance(payload, dict) and "error" in payload:
            error = payload["error"]
            message = error.get("message", "unknown error") if isinstance(error, dict) else str(error)
            raise GogApiError(f"gog: {message}")

        if not isinstance(payload, dict):
            raise GogApiError(f"gog returned unexpected output: {stdout[:200]!r}")

        return payload
