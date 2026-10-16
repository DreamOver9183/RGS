# M4 fix round 2 — CI emulator failure + two review nits (same rules: no git, no shell, only these files)

1. CI failure (GitHub Actions, API 35 emulator with a smaller screen than our local phone):
   `MultiplayerScreenTest.testStateWithFourResults_enablesDecideAndClickCallsOnDecide` fails with `AssertionError` —
   on a shorter screen the 決勝 button is below the fold of the vertically scrollable page, so `performClick()` lands
   outside the viewport and `onDecide` is never called. Make every instrumented test robust to small screens: before
   `assertIsDisplayed()`, `assertIsEnabled()`/`assertIsNotEnabled()` or `performClick()` on a node that can be below the
   fold of a scrollable screen, call `.performScrollTo()` on that node first. Apply this to all tests that render a
   scrollable screen:
   - `app/src/androidTest/java/edu/android/wut2eat/ui/multi/MultiplayerScreenTest.kt` (player buttons of the 2nd row,
     `multi_decide`)
   - `app/src/androidTest/java/edu/android/wut2eat/ui/me/MeScreenTest.kt` (stats, save button, fake-location row)
   - `app/src/androidTest/java/edu/android/wut2eat/ui/location/FakeLocationScreenTest.kt` (preset chips under the map)
   - `app/src/androidTest/java/edu/android/wut2eat/ui/detail/DetailScreenTest.kt` (favorite button)
   - `app/src/androidTest/java/edu/android/wut2eat/ui/favdraw/FavoritesDrawScreenTest.kt` (result card / 詳情)
   Do not use performScrollTo on nodes inside a LazyColumn item that is not composed yet; for the non-lazy
   `verticalScroll` columns above it works directly. Keep each test's intent and assertions.
2. `app/src/main/java/edu/android/wut2eat/ui/me/MeScreen.kt`: after pressing 儲存 the text field keeps the untrimmed
   input while the stored nickname is trimmed. When saving, set the field to `normalizeNickname(nicknameText)` and pass
   that value to `onSaveNickname`.
3. `app/src/main/java/edu/android/wut2eat/ui/location/FakeLocationViewModel.kt`: `locateFailed` stays true after the user
   then picks a preset or a map point. Reset `_locateFailed.value = false` in `pickPreset`, `pickOnMap` and `setEnabled`.
   Add one JVM test to `FakeLocationViewModelTest.kt`: after a failed `useCurrent()`, `pickPreset(...)` clears `locateFailed`.

Reply with the list of files you changed.
