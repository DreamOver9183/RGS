## Summary

- **我的 tab**: no longer a placeholder. It shows a local profile (nickname up to 16 characters and one of six avatar colours, stored on the device under `profile_v1`), the favorites count, the total draw count, and a 自訂定位 settings row (開啟：… / 關閉).
- **Fake location override**: a new 自訂定位 sub-page (`FakeLocationRoute`) turns the override on or off and picks a station preset (台中／台北／新竹／台南／高雄車站), a point on the map, or the real current position (stored under `fake_location_v1`). `OverridableLocationSource` replaces GPS while the override is enabled. `AppContainer` keeps the real `location` and adds `effectiveLocation`, which Home uses for the startup location and the locate button. The multiplayer 附近 pool follows Home's search area, so it uses the fake location too. If the picker map does not load within 10 s, a hint points to the presets.
- **Home chip**: Home shows a 假定位：… chip that opens the settings page, and pans or locates again when the setting changes. A change made during a spin is applied after the result is shown.
- **Resolves the three minor findings deferred from the PR #3 review**:
  - Every navigation callback in `AppRoot` runs only while its back-stack entry is resumed (`ifResumed`) and uses `launchSingleTop`, so a double tap no longer pushes two pages or pops the start destination.
  - `testContainer(..., scope)` and `clearTestDataStores` clean up test DataStores.
  - `AppNavigationTest` now checks the real 我的 content. The unused `PlaceholderScreen` and `coming_soon` are removed.
- **Avatar crash fix**: the UI tests (`MeScreenTest` ×2, `AppNavigationTest.testTabsSwitch`) caught an `ArrayIndexOutOfBoundsException` when opening 我的. `AvatarColors` had five entries while `AVATAR_COUNT` is six. The separate commit `fix(me): define all six avatar colours` resolves it: it adds the sixth colour, clamps colour indices to `AvatarColors`, and adds `AvatarColorsTest` to lock the count.
- **Docs**: AGENTS.md and README.md describe the new tab and page, fake-location semantics, `effectiveLocation` vs `location`, the navigation guard convention, the new persistence keys, test container cleanup, and the updated test counts.

## Test plan

- [x] `testDebugUnitTest`: 91 tests in 29 classes, all passing
- [x] `lintDebug`: 0 errors, 9 warnings (only the known IDs: AndroidGradlePluginVersion, GradleDependency, NewerVersionAvailable ×3, OldTargetApi, DataExtractionRules, DiscouragedApi, LockedOrientationActivity)
- [x] `assembleDebug` and `assembleRelease` (R8) succeed
- [x] `connectedDebugAndroidTest` on an API 37 emulator: 17 tests in 9 classes, all passing (new: `MeScreenTest` ×2, `FakeLocationScreenTest` ×2). Before the fix commit, three of these failed with the avatar crash.
- [x] Manual smoke test on the emulator:
  - 我的 shows the avatar, 美食探險家, the stats, and the 自訂定位 row.
  - Saving the nickname Tester and picking the third colour updates the avatar.
  - The 台北車站 preset turns the override on.
  - Home shows 假定位：台北車站, centred on Taipei.
  - Turning the switch off removes the chip.
  - No crashes in the crash log.
- [ ] Antigravity Gemini review

🤖 Generated with [Claude Code](https://claude.com/claude-code)
