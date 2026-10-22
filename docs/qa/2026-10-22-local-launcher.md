# Local launcher verification — 22 October 2026

`Open Garmin.command` launches a foreground Terminal session. The launcher builds
stale frontend sources, serves the production interface and API together on
127.0.0.1:8765, and opens the browser. Return, Ctrl-C, TERM or HUP cleans up only
its owned server process group. A lock prevents duplicate managed sessions;
unrelated listeners are never terminated. There is no login item or background
service. Closing a browser tab does not quit; the Terminal session owns the app.

Verified with an isolated temporary database, without touching personal records:

- API health and production HTML served successfully.
- Repeated launch reused the managed session.
- Return stopped the server and released its port.
- Immediate second launch worked and retained the same test database.
- Both process cleanup unit tests passed, shell syntax passed, frontend build
  freshness check passed, and git diff whitespace validation passed.

The first restart test exposed a TCP TIME_WAIT conflict in the port probe.
SO_REUSEADDR fixed it; the complete two-launch check then passed.

Finder double-click and Dock placement still require user confirmation. Existing
development servers on 5173/8000 are independent and should be stopped before
daily use. This launcher result does not close the outstanding Friday allocation
check or the normal-use trial and subsequent detailed all-tab QC.
