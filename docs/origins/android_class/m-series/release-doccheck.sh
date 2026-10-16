#!/bin/bash
cd "<repo>" || exit 1
SP="$1"
for f in AGENTS.md README.md; do
  total=$(wc -l < "$f")
  cr=$(grep -c $'\r$' "$f")
  echo "$f: lines=$total crlines=$cr"
  tr -d '\r' < "$f" > "$SP/fmt-$f"
done
sh "$SP/m6-fmtcheck.sh" "$SP/fmt-AGENTS.md" "$SP/fmt-README.md"
echo "fmt-done"
git diff --stat
grep -n -e 'open-now' -e 'open restaurant' -e 'treated as open' -e 'one Places search' -e 'new draw screens' -e 'package migration' -e 'install an `assembleRelease`' -e '營業中' -e '唯一碰' -e '換點重查' AGENTS.md README.md
echo "connect-count: $(grep -c '請連接 API 35' README.md)  playapp-count: $(grep -c 'Play App Signing' README.md)"
grep -n -i -e 'C:\' -e '/c/' -e 'D:\' -e '/d/' -e 'Users/' -e 'AIza' AGENTS.md README.md
echo "path-check-done"
