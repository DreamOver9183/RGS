> **注意：** 這個 PR 疊在 roccadam113/android_class#11（店名精簡）之上，請先合併 #11 再合併本 PR。#11 合併前，本 PR 的 diff 也會包含 #11 的 commit。

## Summary

- **Places shops:** opening the detail page calls Place Details once (`fetchPlace` with `DETAIL_FIELDS`) and shows the real rating with review count, price level, opening hours, editorial summary (店家介紹), and 供餐資訊 chips (dine-in, takeout, delivery, and `serves*` flags). Anything the shop does not provide shows 「Oops，店家沒有提供該資訊」 and is never filled with demo data. There is no 示範資料 badge. A failed fetch shows 暫時無法取得店家資訊 with 重試.
- **Seed and custom shops:** the detail page keeps the labelled demo content (`fakeExtras`) and never calls Places.
- **電話訂餐:** this replaces the detail page's 預訂 button. When the shop has a phone, the button shows the number and opens the system dialer through `Intent.ACTION_DIAL` with a `tel:` URI from the new `telUri`. The user still places the call, so there is no `CALL_PHONE` permission and no Manifest change. The button is disabled without a phone, which is always the case for seed and custom shops.
- **Booking:** the demo booking page is now reached only from the multiplayer winner card's 預訂. The booking page, the 我的 bookings list, and the winner card are unchanged.
- **Billing:** nearby search still requests only the Pro fields in `FIELDS`. Each Place Details request bills at Enterprise + Atmosphere (because of the editorial summary and `serves*` fields). `CachedPlaceDetails`, an in-process LRU of 100 that caches successes only, limits this to one request per Places shop per process.
- **Structure:**
  - domain: `PlaceDetails` / `PlaceService`, plus `telUri` in `Format.kt`.
  - data: `PlaceDetailsSource` and `CachedPlaceDetails`, plus `PlacesSearch.details` / `toDetails`.
  - `AppContainer`: new `placeDetailsSource` parameter. Its default always fails, so tests need no Places.
  - Detail page: `DetailInfo` (`Loading` / `Failed` / `Places` / `Demo`), `DetailViewModel.retryInfo`, and `onCall` → `FoodRouletteRoot.onDial` → `MainActivity.dial`.
- **Docs:** AGENTS.md and README describe the new detail behaviour, the billing split, the booking entry point, and the test counts.

## Test plan

- [x] `./gradlew testDebugUnitTest`: 132 tests in 39 classes, 0 failures, 0 errors, 0 skipped. New or changed tests: `CachedPlaceDetailsTest` (3), `telUri` in `FormatTest`, and `DetailViewModelTest` (Places shop fetches once, seed shop uses demo data without calling Places, NotFound does not call Places, failure then retry).
- [x] `./gradlew connectedDebugAndroidTest` (API 37 emulator, before the final review fixes): 30 tests in 13 classes, 0 failures.
- [x] After the final review fixes, a targeted run of `AppFlowTest` and `DetailScreenTest`: 8 tests, 0 failures. `AppFlowTest` has the renamed `favoritesDraw_opensDetail_withCallOrderDisabled` and the new `multiplayerWinner_bookingAppearsOnMe`. `DetailScreenTest` has two new Places cases.
- [ ] Manual check with a valid Maps key: open a real Places shop's detail page. Check that the rating, price, hours, 店家介紹, and 供餐資訊 match Google Maps, that missing items show the Oops line, and that 電話訂餐 opens the dialer with the number.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
