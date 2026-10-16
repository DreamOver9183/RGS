#!/bin/sh
SP="<scratchpad>"
cd "<repo>" || exit 1
find app -type f -not -path '*/build/*' -exec md5sum {} + | sort -k2 > "$SP/m5-after-fix1.md5"
echo "== main checkout md5 diff =="; diff "$SP/m5-before-fix1.md5" "$SP/m5-after-fix1.md5"
git status --short --untracked-files=all > "$SP/m5-after-fix1.status" 2>/dev/null
echo "== status diff =="; diff "$SP/m5-before-fix1.status" "$SP/m5-after-fix1.status"
cd "<repo>-m4fix" && find app -type f -not -path '*/build/*' -exec md5sum {} + | sort -k2 > "$SP/m4fix-after-fix1.md5"
echo "== m4fix md5 diff =="; diff "$SP/m4fix-before-fix1.md5" "$SP/m4fix-after-fix1.md5"
cd "<repo>"
echo "== trailing newline check =="
git ls-files -m -o --exclude-standard app | while IFS= read -r f; do
  [ -f "$f" ] || continue
  last2=$(tail -c 2 "$f" | od -An -c | tr -s ' ')
  case "$last2" in
    *'\n \n'*|*'\r \n'*) 
      # check CRLF double
      last4=$(tail -c 4 "$f" | od -An -c | tr -s ' ')
      if [ "$(tail -c 2 "$f" | od -An -c | tr -d ' ')" = '\n\n' ]; then echo "OFFENDER(LF LF): $f"; 
      elif [ "$(tail -c 4 "$f" | od -An -c | tr -d ' ')" = '\r\n\r\n' ]; then echo "OFFENDER(CRLF CRLF): $f"; fi ;;
  esac
  if [ "$(tail -c 1 "$f" | od -An -c | tr -d ' ')" != '\n' ]; then echo "NO FINAL NEWLINE: $f"; fi
done
echo "== done =="
