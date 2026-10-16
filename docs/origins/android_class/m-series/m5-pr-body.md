## Summary

- Add a demo-only 預訂 page (`BookingRoute(shopId)`, `ui/booking/`), reachable from the detail page and the multiplayer winner card. It has date chips for the next 14 days (closed weekday disabled), time slots from the fake opening hours (every 30 min until 60 min before closing, only future slots today), a 1–10 party stepper, a booker name prefilled from the nickname, an optional note, validation errors, and a confirmation card with an `FR` + 6-character code. Nothing is sent anywhere.
- Add `domain/Booking.kt` (slots, validation order, codes) and `data/BookingRepository.kt`, which persists bookings under `bookings_v1` (`StoredBooking` in `StoreCodec`).
- `ShopLookup` now resolves ids through registry → favorites → booking snapshots → seed shops.
- The 我的 tab shows an 有效預訂 stat and a 我的預訂 list. Tapping a row opens the shop's detail, and 取消預訂 asks for confirmation, then marks the booking 已取消.
- `AppContainer` takes an injectable `clock` (`java.time.Clock`) for booking dates and slots.
- Docs: AGENTS.md and README.md describe the booking flow, `bookings_v1`, the lookup order, and `clock`. They also explain the `performScrollTo()` rule for UI tests and how to reproduce the short CI screen locally. Test counts are updated.

**Note:** this branch merges `feat/m4-me-fake-location`, so it also contains the CI fix from PR #5 (scroll-to-node in UI tests, nickname field normalisation, clearing the locate-failed message). Those hunks were already identical in the M5 tree and merged cleanly. Once #5 is merged into `main`, they drop out of this diff.

## Test plan

- [x] `testDebugUnitTest`: 103 tests in 32 classes, 0 failures
- [x] `lintDebug`: 0 errors, 11 warnings (new: 2 × `ModifierParameter` in `MeScreen` / `MultiplayerScreen`)
- [x] `assembleDebug` and `assembleRelease` (R8)
- [x] `connectedDebugAndroidTest` on a small screen (`wm size 720x1280`, `wm density 320`, like CI): 19/19 in 10 classes
- [x] `connectedDebugAndroidTest` on the normal emulator screen: 19/19 in 10 classes
- [x] Manual smoke test on the emulator: 收藏 → detail → 預訂 → pick date, time, and party → validation message → 確認預訂 shows the code → 完成 → 我的 lists the booking (有效預訂 1) → 取消預訂 → 已取消 (有效預訂 0); no crashes
- [ ] Antigravity Gemini review

🤖 Generated with [Claude Code](https://claude.com/claude-code)
