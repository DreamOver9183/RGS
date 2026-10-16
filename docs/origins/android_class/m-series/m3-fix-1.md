# M3 review round 1 — fix exactly these points (same rules: no git, no shell, only these files)

Build compiles; 70 of 71 JVM tests pass. Reviewer findings:

1. FAILING TEST — `app/src/test/java/edu/android/wut2eat/ui/multi/MultiplayerViewModelTest.kt`,
   `testCacheReusedForSameAreaAndRefetchedAfterAreaChanges`: NPE at `slots[2].reel!!` after the area changes to
   (25.0400, 121.5000). The fake search still returns only the Taichung shop (~120 km away), so `drawShop` → `usable()`
   filters it out (outside the 3 km radius), the pool is empty, the slot gets `message = Empty` and no reel. The
   ViewModel is right; the test data is wrong. Make the fake return a shop near whichever point it is queried for
   (e.g. `customSearch = { pt, _ -> listOf(shopNear(pt)) }`, or a second shop near the new centre returned after the
   area change), and re-check the expected search-call counts (one fetch for the first area, exactly one more after the
   area change).
2. `app/src/main/java/edu/android/wut2eat/ui/favdraw/FavoritesDrawViewModel.kt`, `draw()`: the `Spinning` guard is only
   set after `favorites.favorites.first()` suspends, so a fast double tap launches two draws (two reels, two `onDrawn`
   calls → the draw counter is incremented twice). Add a private `var drawing = false` that `draw()` checks and sets
   synchronously before launching, and resets in a `finally` at the end of the coroutine. Add a JVM test to
   `FavoritesDrawViewModelTest.kt`: calling `draw()` twice in a row results in exactly one `onDrawn` call.
3. `app/src/main/java/edu/android/wut2eat/ui/multi/MultiplayerViewModel.kt`, `decide()` (and the same pattern in
   `draw()`): do not perform side effects (`gate.begin()`, `rand()`, writing captured vars) inside the
   `_state.update { }` lambda — `update` may re-run the lambda on contention. All calls happen on the main thread, so
   read `val s = _state.value`, check the guards, compute `results`/`idx`/`id`/`spin` outside, then apply a pure
   `_state.update { it.copy(...) }`. Keep the behaviour and the existing tests' expectations.
4. `app/src/androidTest/java/edu/android/wut2eat/ui/nav/AppNavigationTest.kt` (you correctly flagged this — you may now
   edit it): in `testTabsSwitch`,
   - after selecting 收藏, wait for and assert the seeded demo shop: `rule.waitUntil(TIMEOUT_MS) { rule.onAllNodesWithText("綠川拉麵屋").fetchSemanticsNodes().isNotEmpty() }`;
   - after selecting 多人, assert the multiplayer page instead of `coming_soon`:
     `rule.onNodeWithText(string(R.string.multi_draw_player, 1)).assertIsDisplayed()`;
   - after selecting 我的 (still a placeholder in this milestone), assert `coming_soon` is displayed.
   Keep the rest of the test and the second test unchanged.

Reply with the list of files you changed.
