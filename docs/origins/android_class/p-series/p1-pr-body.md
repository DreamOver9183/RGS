## Summary

- Many Google Maps listings append promotional words to the shop name after a vertical bar (for example `SIX STAR 六星炸雞(勤美英才店) ft.卜蜂商店 |台中美食|必吃炸雞|炸物推薦`). The new domain function `cleanShopName` (`domain/ShopName.kt`) keeps the trimmed text before the first `|`, `｜`, `丨`, or `│`; if nothing is left before the separator it returns the trimmed original. Other symbols (`-`, `–`, `【】`, `()`, `ft.`) are left alone.
- Applied in `PlacesSearch.toShops`: new Places results get the short name, and a place whose cleaned name is blank is skipped, as one without a display name is.
- Applied in `StoredShop.toShop()` for Places ids only (`isPlacesShop`): Places favorites and booking snapshots already saved on the device are cleaned when read, without rewriting DataStore. `custom:` and `seed:` shop names stay as entered, even when they contain `|`.
- Docs: AGENTS.md (domain, data, and JVM test sections) and README (Home result and detail page notes, JVM test coverage and counts) describe the rule.

## Test plan

- [x] `./gradlew testDebugUnitTest`: 126 tests in 38 classes, 0 failures, 0 errors, 0 skipped. New: `ShopNameTest` (5 tests) and `StoreCodecTest.testDecode_cleansPlacesShopName_preservesCustomAndSeed`.
- [ ] Manual check with a valid Maps key: a Home draw over a shop with a `|` in its Google Maps name shows the short name.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
