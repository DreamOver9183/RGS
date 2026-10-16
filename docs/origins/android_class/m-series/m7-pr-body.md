## Summary

Milestone M7: end-to-end flows and release hardening (the last milestone of the 10-screen plan).

- **`AppFlowTest`** (3 end-to-end Compose tests on the full app with a test `AppContainer`): 收藏 → 從收藏抽 → 詳情 → 預訂 → the booking code shows on 我的; 新增餐廳 → the shop appears in 收藏 and the favorites-draw pool grows to 7; Home result → share icon → 分享給朋友 hands text with the shop name and Maps link to the share callback.
- **Accessibility / UX:** 我的 avatar colours are 48dp `selectable` radio items; booking errors clear as soon as the form is edited and, like the add-shop type error, use the theme's error colour; FilterChips use the app palette (`secondaryContainer`, `outlineVariant`) instead of Material lavender; 自訂定位 shows 未設定 when never set and the map can be dragged without scrolling the page; the share card uses the shared `Avatar` with the profile colour; the share sheet shows its title (`EXTRA_TITLE`).
- **Runtime hardening:** request the latest Maps renderer at start-up (right after a reboot Play services sometimes picked the legacy renderer, which never reported the map as loaded); Places is initialised with `Locale.TAIWAN` so type names are Chinese on any device language.
- **R8:** ran `:app:analyzeReleaseR8Config`; removed the `data/store` keep rule, which the analyzer showed is fully covered by kotlinx.serialization's consumer rules (kept items identical before/after). The `ui.nav` route rule and the broad `domain.**` rule stay (documented why).
- **Docs:** README lists all 10 screens and how to reach each; AGENTS.md covers the new behaviour, end-to-end test conventions, the R8 analysis command and keep-rule rationale, and a troubleshooting entry for the legacy renderer.

## Testing

- `testDebugUnitTest`: 116 tests / 36 classes green (new: a booking edit clears the error message).
- `lintDebug`: 0 errors (9 pre-existing build/manifest warnings). `assembleDebug`, `assembleRelease` (R8) and `:app:analyzeReleaseR8Config` pass.
- `connectedDebugAndroidTest`: 26 tests / 13 classes green on both a 720x1280 / 320 dpi display (like CI) and the normal emulator display.
- Manual smoke on the emulator: chip colours, 48dp avatar hit area, 未設定 + map drag on 自訂定位, booking error clearing, share avatar and share-sheet title, Chinese Places type names on Home.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
