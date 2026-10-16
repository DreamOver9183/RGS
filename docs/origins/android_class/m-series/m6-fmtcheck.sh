#!/bin/sh
# usage: m6-fmtcheck.sh file...
for f in "$@"; do
  [ -f "$f" ] || continue
  # trailing newline check
  last=$(tail -c 1 "$f" | od -An -c | tr -d ' ')
  last2=$(tail -c 2 "$f" | od -An -c | tr -d ' ')
  if [ "$last" != '\n' ]; then echo "$f: no trailing newline"; fi
  if [ "$last2" = '\n\n' ]; then echo "$f: multiple trailing newlines"; fi
  if grep -q $'\r' "$f"; then echo "$f: contains CR"; fi
  awk -v F="$f" '{ sub(/\r$/, "") } /^[ \t]*$/ { if (prev) print F ":" NR ": consecutive blank line"; prev=1; next } { prev=0 }' "$f"
done
