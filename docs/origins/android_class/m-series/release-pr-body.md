## Summary

Prepares the v1.0.0 release. Nothing is published by this PR: the GitHub Release and its APK are created after merge, following the new recipe.

### Version bump
- `app/build.gradle.kts`: `versionCode` 1 → 2, `versionName` 0.1.0 → 1.0.0 (only these two lines change).
- Two stale comments that still described placeholder pages are refreshed (comment-only):
  - `ui/nav/Routes.kt`: the file comment no longer says sub-page routes are added milestone by milestone.
  - `ui/nav/AppNavigationTest.kt`: the `testTabsSwitch` KDoc now says what the test checks (each tab is selected and shows its real content) instead of 即將推出.

### Release procedure
- AGENTS.md: the toolchain list now includes the app version, and there is a new **Publish a release** recipe:
  - Bump the version in a PR.
  - Build from `main` after the merge. The asset is the debug-signed `assembleDebug` APK, renamed to `food-roulette-vX.Y.Z.apk`. `assembleRelease` only gives an unsigned APK that cannot be installed.
  - Run `gh release create vX.Y.Z … --target main` on the merge commit. Use `--prerelease` only for previews.
  - The APK embeds the builder's `MAPS_API_KEY`. Maps work only where the key allows the signing SHA-1.
  - Never attach or commit keystores or `local.properties`.
  - To check R8 at runtime, sign the release APK locally with `apksigner` and the debug keystore, and commit no signing config.
- The R8 keep-rules sentence that said to "install an `assembleRelease` build" now points to that recipe.
- README: a new **版本與下載** section covers the current version, where the Releases APK lives (debug-signed, Android 15+), what the key must allow, and how to build it yourself.

### Audit corrections (AGENTS.md / README.md)
- **Business-status filter:** "open-now" / "open restaurants" / 營業中 now name the actual filter, the Places business status `OPERATIONAL`. Pool draws apply no business-status or radius filter.
- **Multiplayer 附近 pool:** "one Places search" becomes "one sampling run (at most 3 Places searches, `MAX_TRIES`)". README: 最多查 3 次（含第一次） and 同一區域只跑一次抽樣.
- **`mapsUrl`:** documented in `domain/Format.kt`, not ShopIds. `Places.kt` (`Shop`, `usable`) and `Sample.kt` (`drawShop`) are now described.
- **Renamed references:**
  - `FavoritesDrawScreen` and `MultiplayerScreen` replace "the new draw screens".
  - "Package migration" becomes "when changing the package identity".
- **`FakeLocationScreenTest`:** the saved-preset test is now described accurately (台中車站 selected, 台北車站 not). `RoutesSerializationTest` is documented as covering only the four tab routes.
- **CI artifacts:** JUnit/lint reports are always uploaded, the debug APK on success, and the R8 mapping on failure. The release APK is not uploaded.
- **Newly documented behaviour:**
  - `FoodRouletteRoot`'s `onReload`: MainActivity clears the ViewModelStore and recreates the activity to retry after a fatal error.
  - `Shop.note`: a custom shop's address or note. The detail page shows it when it is not blank, and it is stored in favorites, custom shops and booking snapshots.
- **Files added to the structure section:**
  - `data/SettingsStore.kt` (`RadiusStore`)
  - `data/LocationProvider.kt` (`LocationSource`/`FusedLocationSource`, 10 s timeout)
  - `ui/theme/Icons.kt` (`FoodIcon`)
  - `FakeLocationPage` / `MePage`, located in their `*Screen.kt` files
- **README:**
  - The only Places boundary is `PlacesSearch`, not `ShopLookup`.
  - Added `MainActivity.kt` to the project tree.
  - Completed the `di/` line.
  - Removed the duplicated signingReport/Play App Signing paragraph and the duplicated "請連接 API 35 以上…" sentence.
  - The detail-page items mention a custom shop's 地址或備註.

## Verification
- `./gradlew testDebugUnitTest lintDebug assembleDebug assembleRelease`: **BUILD SUCCESSFUL**.
  - 120 JVM tests in 37 classes, 0 failures.
  - lint: 0 errors, 7 warnings (version/target-API and other pre-existing warnings, none from this change).
- `aapt2 dump badging` on `app-debug.apk` and `app-release-unsigned.apk`: `versionCode='2' versionName='1.0.0'`.
- Docs: one trailing newline each, no consecutive blank lines, no local paths, commit hashes or secrets.
- Not run: `connectedDebugAndroidTest`. The only androidTest change is a KDoc comment, and CI's `instrumented` job runs it.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
