## Summary

- **收藏 tab is live:** favorites are listed newest first, with distances from Home's current search centre, and can be removed. On first run the app seeds six fictional demo shops near Taichung Station (`seed:` ids). The seeding runs only once, so shops the user removes are not re-added.
- **Restaurant detail sub-page:** shows name, type, and distance. Below that is a section labelled 示範資料 with deterministic fake rating, price level, opening hours, intro, and signature dishes. The page also has a favorite toggle and an "open in Google Maps" button. Routes carry only a shop id, which `ShopLookup` resolves through recently drawn shops (`Session.registry`), then favorites, then seed shops; an unknown id shows a not-found state.
- **Home result row:** adds a ♡ favorite toggle and a 詳情 button. The ViewModel reports its search area and each drawn shop through `RouletteHooks`.
- **Persistence:** favorites are stored as JSON in the existing single `settings` Preferences DataStore. The codec (`data/store/StoreCodec.kt`) uses versioned keys (`favorites_v1`, `seeded_v1`), and corrupt data decodes to defaults. A ProGuard keep rule covers the DTOs.
- **Screen convention:** each new screen has `XxxViewModel`, a stateless `XxxScreen`, and a stateful `XxxPage` that uses `LocalAppContainer`. Sub-pages use `SubPageScaffold`.
- **Docs:** AGENTS.md and README describe the new structure, data flow, persistence rules, screen recipe, Places data-storage caveat, and test coverage.

## Test plan

- [x] `testDebugUnitTest`: 56 JVM tests in 17 classes pass
- [x] `lintDebug`: 0 errors, 9 warnings (no new warning ids)
- [x] `assembleDebug` and `assembleRelease` (R8) succeed
- [x] `connectedDebugAndroidTest`: 10 tests in 5 classes pass on an API 37 emulator
- [x] Manual smoke test on the emulator:
  - The 收藏 tab shows the 6 seeded demo shops.
  - A card opens the detail page with the 示範資料 badge.
  - Back navigation works.
  - 多人 and 我的 open without a crash.
  - A Home draw shows the ♡ and 詳情 buttons.
- [ ] Antigravity Claude Opus review

🤖 Generated with [Claude Code](https://claude.com/claude-code)
