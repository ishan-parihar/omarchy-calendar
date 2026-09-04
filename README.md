# Calendar for Omarchy (gog edition)

**Your Google Calendar, in your Omarchy bar.** Fork of
[tmn73/omarchy-calendar](https://github.com/tmn73/omarchy-calendar) with the
sync backend replaced by [gog](https://gogcli.sh), a single-binary Google
Workspace CLI. The widget UI is unchanged; only how events get fetched differs. A month view with your real
events on it, and a bar that tells you what is coming before it starts.

Not a Google user? It reads a plain JSON file, so khal, vdirsyncer, Nextcloud
or an ICS feed work just as well. See [Use another source](#use-another-source).

![Preview](preview.png)

It replaces the built-in clock rather than sitting beside it, so you keep one
icon. Left click opens a month calendar with your real events on it. When
something is close, the bar itself stops being just a clock and tells you:

![The bar announcing the next event](docs/images/bar.png)

The clock stays. This widget takes the desktop clock's place, so trading the
time away for an event title would be a downgrade you pay for all day.

## Features

- Month grid with ISO week numbers, coloured dots per calendar
- The selected day's agenda under the grid, click any day to see it
- The next event today, with a live countdown, in the panel header
- The bar label announces what is next, minutes before it starts
- A **Join** button on meetings that have a video link, shown only from 15
  minutes before the start until 15 minutes after the end
- Clicking any event opens it in your calendar
- Per-calendar visibility, week start, and countdown lead time in a settings page
- Google's working-location markers hidden by default, declined invitations
  struck through
- Everything the built-in Omarchy clock does: label formats, right click to
  cycle them, the year and life progress bars if you want them back
- Theme aware, because it is a fork of the built-in clock

## Requirements

Omarchy 4 with Quickshell. Google Calendar is optional, see
[Use another source](#use-another-source).

## Install

```bash
omarchy plugin add https://github.com/ishan-parihar/omarchy-calendar.git --enable
```

This widget **replaces** the built-in clock. In `~/.config/omarchy/shell.json`,
remove the `omarchy.clock` entry from `bar.layout.center` and point
`bar.centerAnchor` at `tmn73.calendar`:

```json
{
  "bar": {
    "centerAnchor": "tmn73.calendar",
    "layout": {
      "center": [
        { "id": "tmn73.calendar", "format": "dddd HH:mm" }
      ]
    }
  }
}
```

Then:

```bash
omarchy restart shell
```

**Installing is not the whole job.** At this point you have a working clock and
an empty calendar, because nothing is feeding it yet. Connect Google Calendar
below, or point any other source at the file. The widget says as much when you
open it, with the command to run.

## Sync your Google Calendar

Prerequisite: [gog](https://gogcli.sh) (`go install
github.com/openclaw/gogcli/cmd/gog@latest`, or a release binary).

```bash
~/.config/omarchy/plugins/tmn73.calendar/sync/setup
```

Run it in a real terminal. It pauses for input, and two steps have to be done
by hand in the Google Cloud Console.

**You need your own Google OAuth client.** There is no shared one, and that is
not laziness. Calendar access is a Google *sensitive* scope, so a publicly
distributed client would need Google verification and is capped at 100 users
until it gets it. This is exactly why `gcalcli`'s shared token is currently
restricted. Every user brings their own credentials.

The script automates what has an API:

- storing the downloaded client secret (`gog auth credentials`)
- the scoped login (`gog auth add --services calendar --readonly`)
- verifying calendar access, and recording your account plus gog's absolute
  path in `calendar-sync.json` (a systemd timer does not inherit your
  shell's `PATH`, so the bare name is not enough)
- the systemd timer

It stops and waits for the two things Google exposes no API for: creating
the Desktop OAuth client, and publishing the app. Each one prints the exact
URL.

The publish step is a trap, and the script says so at the time:
**publish the app.** While it sits in Testing, Google expires refresh tokens
after seven days and your calendar quietly stops updating. Unverified
production apps show a one time warning screen and then work indefinitely.

When it finishes, events land in `~/.local/state/omarchy/calendar-events.json`
every five minutes and the widget picks them up without a restart.

How a sync works: one `gog calendar events --all --json` call across all
calendars (read-only, non-interactive), mapped onto the same event file the
widget has always read. The old `gws` + `gcloud` + per-calendar Python
machinery is gone; `sync/omarchy_calendar_sync/` is now a thin `gog`
adapter (`gog.py`), the unchanged contract writer (`contract.py`), and the
unchanged normalizer (`normalize.py`).

## Use another source

The widget has no idea Google exists. It reads one file and renders it:

```
~/.local/state/omarchy/calendar-events.json
```

Anything that writes that file works: khal, vdirsyncer, Nextcloud, an ICS feed,
a shell script, a cron job of your own. No credentials, no network, no `gws`.

```json
{
  "version": 1,
  "syncedAt": "2026-08-10T16:42:00+00:00",
  "source": "whatever produced this",
  "events": [
    {
      "id": "any-stable-id",
      "calendarId": "work@example.com",
      "calendarName": "Work",
      "color": "#f83a22",
      "dateKey": "2026-08-10",
      "start": "2026-08-10T19:15:00-05:00",
      "end": "2026-08-10T20:15:00-05:00",
      "allDay": false,
      "title": "Tax filing",
      "location": ""
    }
  ]
}
```

These four extra fields are optional. Omit them and everything still works:

| Field | Effect |
|---|---|
| `meetingUrl` | Shows the **Join** button around the event's time. Must be `https`, anything else is dropped |
| `eventUrl` | Clicking the row opens this. Must be `https` |
| `eventType` | `workingLocation` is hidden by default, `outOfOffice` is labelled |
| `responseStatus` | `declined` is struck through, and can be hidden entirely |

Rules a writer has to follow:

- `dateKey` is `YYYY-MM-DD` in local time, and it is what the grid keys on.
- A multi-day event is emitted **once per day it covers**, each row with its own
  `dateKey`. Those rows share an `id`, so the unique key for a row is
  `id + dateKey`.
- `allDay` events are excluded from the countdown, since counting down to
  midnight tells you nothing.
- Write the file atomically, temp file then rename. The widget watches it.
- Unknown fields are ignored, so you can add your own.

`tests/fixtures/calendar-events.json` is a valid two-event file to start from.

## Settings

Click the clock, then the gear icon in the panel header.

![The settings page](docs/images/settings.png)

| Section | What it does |
|---|---|
| Calendars | Show or hide each calendar. The list comes from your own events, so it needs no configuration |
| Week starts on Monday | Off starts the week on Sunday |
| Working location events | Google's work-from-home markers. Hidden by default because they are all-day rows describing no commitment |
| Declined invitations | On lists them struck through, off hides them entirely |
| Year and life progress | Brings back the built-in clock's bars, off by default |
| Bar label | How early the bar announces what is next: never, 5, 15, 30 or 60 minutes |
| Sync | Event count, source and last sync time, for diagnosing a quiet calendar |

Hiding a calendar is instant and does not change what the sync fetches, so
bringing one back does not wait for the next run.

Sync behaviour lives in `~/.config/omarchy/calendar-sync.json`:

```json
{
  "account": "you@gmail.com",
  "gogPath": "/absolute/path/to/gog",
  "calendars": { "include": [], "exclude": [] },
  "window": { "pastDays": 7, "futureDays": 60 }
}
```

`include: []` means all of them. Names and ids both match. `account` selects
the gog account (empty means gog's default). `gogPath` has to be absolute: a
systemd user service does not inherit your shell's `PATH`, so a `gog`
installed by `go install` (`~/go/bin`) is invisible to it under its bare name.

## Troubleshooting

```bash
journalctl --user -u omarchy-calendar-sync -f
systemctl --user list-timers omarchy-calendar-sync.timer
```

| Symptom | Cause |
|---|---|
| `sync failed` / auth error | No valid credentials. Check `gog auth list --check` and `gog auth doctor --check`; re-run `sync/setup`, or `gog auth add you@gmail.com --services calendar --readonly --force-consent` |
| Empty calendar list or `403` | The calendar scope was never granted (consent checkbox left unticked) or the Calendar API is not enabled for your Cloud project. Fix both, then log in again |
| `invalid_grant` | The refresh token expired. Almost always an app left in Testing, which caps refresh tokens at seven days. Publish it, then log in again |
| `gog is not installed or not on PATH` from the timer, but it works in your terminal | `gogPath` is not absolute. `sync/setup` writes it for you |
| The panel says "No calendar synced yet" | The events file does not exist. The sync has never completed |
| The panel says the calendar may be out of date | The file exists but `syncedAt` is old. Check the journal above |
| An event shows up twice | Two of your calendars both carry it. Hide one in settings. The sync already drops exact duplicates by iCalUID and start time |
| `The project ID you specified is already in use` during setup | Fixed in 0.1.1. Google Cloud project ids are unique across all of Google, and older versions hardcoded one. Update the plugin, or pass your own: `PROJECT_ID=something-unique sync/setup` |
| Clicking an event opens your calendar but not the event | The link resolves only for the Google account the sync authenticated as. If your browser opens it in a profile signed into a different account, Google falls back to the calendar root. Route `google.com/calendar` to the profile holding that account |
| The Join button never appears | It only shows from 15 minutes before the start until 15 minutes after the end, and only when the event has a video link |
| Events are off by a day | Report it. Timezone handling resolves a named IANA zone precisely to avoid this, and there is a regression test for daylight saving transitions |

## Uninstall

```bash
systemctl --user disable --now omarchy-calendar-sync.timer
rm ~/.config/systemd/user/omarchy-calendar-sync.{service,timer}
systemctl --user daemon-reload
omarchy plugin remove tmn73.calendar
```

Then put `omarchy.clock` back in `shell.json` and `omarchy restart shell`.

Your Google credentials live in gog's own store (OS keyring by default; see
`gog auth list` and https://gogcli.sh) and are not touched by any of this.
Remove the account there to revoke locally, and remove the project from your
Google Cloud console to revoke properly.

## Development

```bash
cd sync && PYTHONPATH=. python3 -m unittest discover -s ../tests -t .. -v
node --test tests/model.test.js
```

No dependencies, no dev dependencies. The Python sync is standard library only
and the QML logic lives in `Model.js`, which loads under Node precisely so it
can be tested.

`Panel.qml` and `BarWidget.qml` are not unit tested. Quickshell widgets need a
live shell to render, and building that harness would cost more than it catches.
Anything worth testing was deliberately pushed down into `Model.js`.

## License

MIT. Derived from Omarchy's built-in clock plugin, whose copyright notice is
kept in `LICENSE`, via [tmn73/omarchy-calendar](https://github.com/tmn73/omarchy-calendar).
Upstream UI and contract copyright remains with its authors; the gog sync
backend is new in this fork.
