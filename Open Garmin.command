#!/bin/zsh
# Finder supplies a limited PATH; use the installed local runtimes as well.
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
cd -- "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  print 'The local Python environment is missing. Run make setup first.'
  read '?Press Return to close. '
  exit 1
fi
exec .venv/bin/python scripts/local_app.py
