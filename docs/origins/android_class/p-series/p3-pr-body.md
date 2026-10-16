> **注意：** 這個 PR 疊在 roccadam113/android_class#11（店名精簡）與 #12（詳情頁 Place Details）之上，需依序先合併 #11、#12。兩者都已合併進 `main`，因此本 PR 的 diff 只包含第三段（抽籤頁篩選）。

## Summary

- **Filters on Home:** a 篩選 button next to the radius opens a bottom sheet (`FilterSheet`, Material 3 `ModalBottomSheet`) with four filters:
  - 最低星等: 不限, 3.5★, 4.0★, or 4.5★ 以上; one choice.
  - 消費級距: $ to $$$$; any combination.
  - 只抽營業中的店: a switch.
  - 餐廳類型: 小吃, 速食, 咖啡廳, or 早午餐; any combination.

  The button shows 篩選（n） while filters are active and is disabled while the reel spins. 清除篩選 resets everything.
- **Type filter runs on Google's side:** the chosen `FoodCategory` types become the nearby search's `includedPrimaryTypes`. This costs nothing extra.
- **Enterprise fields only when needed:** rating, price level, current opening hours, and UTC offset (`FILTER_FIELDS`) are requested only while the rating, price, or open-now filter is on. That search then bills as Nearby Search Enterprise. Otherwise every search keeps the Pro `FIELDS`.
- **Missing data is excluded:** with a filter on, a shop without that data (for example no price level) is not drawn (`matchesFilter`). `openNow` comes from the current opening-hours periods at the place's UTC offset (`OpeningHours.kt`; overnight and week-wrap periods supported). When nothing matches, Home shows `info_empty_filtered`.
- **Saved on the device:** the filter is stored as JSON under `filter_v1` (`DataStoreFilterStore`) and restored at start-up. The decoder sanitises invalid values. The new `Shop.rating`, `priceLevel`, and `openNow` fields are never stored.
- **Home only:** the multiplayer 附近 pool (`NearbyPoolCache`) and the favorites draws ignore the filter. `drawShop`'s new `query` and `accept` parameters default to the old behaviour.
- **Docs:** AGENTS.md and README describe the filters, the billing rule, the stored key, and the new test counts.

## Test plan

- [x] `./gradlew testDebugUnitTest`: 152 tests in 41 classes, 0 failures, 0 errors, 0 skipped. Added: `FilterTest` (6), `OpeningHoursTest` (6), a `SampleTest` case for `query`/`accept`, `StoreCodecTest` filter round trip and sanitising (3), and `RouletteViewModelTest` filter cases (4, including an unchanged filter keeping the result).
- [x] `./gradlew connectedDebugAndroidTest` (API 37 emulator, before the final review fixes): 31 tests in 14 classes, 0 failures. This includes the new `FilterSheetTest`.
- [x] After the final review fixes, a targeted run of `FilterSheetTest` and `RouletteScreenTest`: 4 tests, 0 failures.
- [ ] Manual check with a valid Maps key on a real location: try each filter (minimum rating, each price level, 營業中, and each 餐廳類型) and check that the drawn shops match Google Maps and that 清除篩選 and the saved filter after restart work.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
