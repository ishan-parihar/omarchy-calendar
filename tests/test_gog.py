import json
import unittest
from pathlib import Path

from omarchy_calendar_sync import gog

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text()


class FakeRunner:
    """Records argv and replays canned responses keyed by a marker in argv."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, argv, env):
        self.calls.append((argv, env))
        for marker, response in self.responses.items():
            if marker in argv:
                return response
        raise AssertionError(f"unexpected argv: {argv}")


class TestVersion(unittest.TestCase):
    def test_parses_version_line(self):
        client = gog.Gog(runner=FakeRunner({"--version": (0, "v0.39.0\n", "")}))
        self.assertEqual(client.version(), (0, 39, 0))

    def test_missing_binary_raises(self):
        def runner(argv, env):
            raise FileNotFoundError("gog")

        with self.assertRaises(gog.GogMissing):
            gog.Gog(runner=runner).check()

    def test_old_version_raises(self):
        client = gog.Gog(runner=FakeRunner({"--version": (0, "v0.29.9\n", "")}))
        with self.assertRaises(gog.GogTooOld):
            client.check()

    def test_current_version_passes(self):
        client = gog.Gog(runner=FakeRunner({"--version": (0, "v0.39.0\n", "")}))
        client.check()


class TestCalendars(unittest.TestCase):
    def test_maps_to_id_name_color(self):
        client = gog.Gog(runner=FakeRunner({"calendars": (0, fixture("gog-calendars.json"), "")}))
        calendars = client.calendars()
        self.assertEqual(
            calendars,
            [
                {"id": "a@example.com", "name": "Personal", "color": "#f83a22"},
                {"id": "b@example.com", "name": "Phases of the Moon", "color": "#fad165"},
            ],
        )

    def test_missing_color_falls_back(self):
        body = json.dumps({"calendars": [{"id": "x", "summary": "No Color"}]})
        client = gog.Gog(runner=FakeRunner({"calendars": (0, body, "")}))
        self.assertEqual(client.calendars()[0]["color"], gog.FALLBACK_COLOR)

    def test_missing_summary_falls_back_to_id(self):
        body = json.dumps({"calendars": [{"id": "x@example.com", "backgroundColor": "#ffffff"}]})
        client = gog.Gog(runner=FakeRunner({"calendars": (0, body, "")}))
        self.assertEqual(client.calendars()[0]["name"], "x@example.com")

    def test_fetches_all_pages_as_json(self):
        runner = FakeRunner({"calendars": (0, fixture("gog-calendars.json"), "")})
        gog.Gog(runner=runner).calendars()
        argv = runner.calls[0][0]
        self.assertIn("--all", argv)
        self.assertIn("--json", argv)

    def test_account_flag_is_passed_when_configured(self):
        runner = FakeRunner({"calendars": (0, fixture("gog-calendars.json"), "")})
        gog.Gog(account="you@gmail.com", runner=runner).calendars()
        argv = runner.calls[0][0]
        self.assertEqual(argv[argv.index("--account") + 1], "you@gmail.com")

    def test_safety_flags_are_always_passed(self):
        runner = FakeRunner({"calendars": (0, fixture("gog-calendars.json"), "")})
        gog.Gog(runner=runner).calendars()
        argv = runner.calls[0][0]
        self.assertIn("--no-input", argv)
        self.assertIn("--readonly", argv)


class TestEvents(unittest.TestCase):
    def test_returns_raw_items_with_calendar_ids(self):
        client = gog.Gog(runner=FakeRunner({"events": (0, fixture("gog-events.json"), "")}))
        items = client.events("2026-08-01T00:00:00+00:00", "2026-09-01T00:00:00+00:00")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "evt1")
        self.assertEqual(items[0]["calendarId"], "a@example.com")

    def test_single_call_covers_all_calendars_with_window(self):
        runner = FakeRunner({"events": (0, fixture("gog-events.json"), "")})
        gog.Gog(runner=runner).events("MIN", "MAX")
        self.assertEqual(len(runner.calls), 1)
        argv = runner.calls[0][0]
        self.assertIn("--all", argv)
        self.assertIn("--all-pages", argv)
        self.assertIn("--json", argv)
        self.assertEqual(argv[argv.index("--from") + 1], "MIN")
        self.assertEqual(argv[argv.index("--to") + 1], "MAX")
        self.assertEqual(argv[argv.index("--sort") + 1], "start")


class TestErrors(unittest.TestCase):
    def test_auth_required_exit_code_raises_auth_error(self):
        runner = FakeRunner({"events": (4, "", "no valid credentials: run gog auth add")})
        client = gog.Gog(runner=runner)
        with self.assertRaises(gog.GogAuthError):
            client.events("MIN", "MAX")

    def test_permission_denied_exit_code_raises_auth_error(self):
        runner = FakeRunner({"events": (6, "", "insufficient scopes")})
        client = gog.Gog(runner=runner)
        with self.assertRaises(gog.GogAuthError):
            client.events("MIN", "MAX")

    def test_other_exit_code_raises_api_error_naming_code_and_stderr(self):
        runner = FakeRunner({"events": (1, "", "something broke")})
        client = gog.Gog(runner=runner)
        with self.assertRaises(gog.GogApiError) as context:
            client.events("MIN", "MAX")
        message = str(context.exception)
        self.assertIn("1", message)
        self.assertIn("something broke", message)

    def test_error_object_in_body_raises_api_error(self):
        body = json.dumps({"error": {"message": "boom"}})
        client = gog.Gog(runner=FakeRunner({"events": (0, body, "")}))
        with self.assertRaises(gog.GogApiError):
            client.events("MIN", "MAX")

    def test_unparseable_stdout_raises_api_error(self):
        client = gog.Gog(runner=FakeRunner({"events": (0, "not json", "")}))
        with self.assertRaises(gog.GogApiError):
            client.events("MIN", "MAX")

    def test_non_object_output_raises_api_error(self):
        client = gog.Gog(runner=FakeRunner({"events": (0, "[1, 2]", "")}))
        with self.assertRaises(gog.GogApiError):
            client.events("MIN", "MAX")


if __name__ == "__main__":
    unittest.main()


class TestConfigurableBinary(unittest.TestCase):
    def test_defaults_to_the_bare_name(self):
        runner = FakeRunner({"--version": (0, "v0.39.0\n", "")})
        gog.Gog(runner=runner).version()
        self.assertEqual(runner.calls[0][0][0], "gog")

    def test_uses_an_absolute_path_when_configured(self):
        runner = FakeRunner({"--version": (0, "v0.39.0\n", "")})
        gog.Gog(runner=runner, binary="/home/user/go/bin/gog").version()
        self.assertEqual(runner.calls[0][0][0], "/home/user/go/bin/gog")

    def test_empty_binary_falls_back_to_the_bare_name(self):
        runner = FakeRunner({"--version": (0, "v0.39.0\n", "")})
        gog.Gog(runner=runner, binary="").version()
        self.assertEqual(runner.calls[0][0][0], "gog")

    def test_missing_binary_message_names_it_and_explains_path(self):
        def runner(argv, env):
            raise FileNotFoundError(argv[0])

        with self.assertRaises(gog.GogMissing) as caught:
            gog.Gog(runner=runner, binary="/home/user/go/bin/gog").check()
        message = str(caught.exception)
        self.assertIn("/home/user/go/bin/gog", message)
        self.assertIn("gogPath", message)
