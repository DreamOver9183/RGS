# M2 review round 2 — two instrumented tests fail on the emulator (fix the TESTS only; same rules: no git, no shell)

`connectedDebugAndroidTest` result: 8 passed, 2 failed. Both failures are test-code mistakes; do not change app code.

1. `app/src/androidTest/java/edu/android/wut2eat/ui/detail/DetailScreenTest.kt`,
   `testLoadedState_showsContentAndFavoriteToggleCallsCallback`:
   `AssertionError: Expected at most 1 node but found 2 nodes that satisfy (Text … contains 'Fantastic Ramen')` —
   the loaded shop name is shown both as the top-app-bar title and as the page heading, so `onNodeWithText(name)` is
   ambiguous. Replace that assertion with `rule.onAllNodesWithText(name).assertCountEquals(2)` (import
   `androidx.compose.ui.test.onAllNodesWithText` and `androidx.compose.ui.test.assertCountEquals`). Keep the other
   assertions of that test.
2. `app/src/androidTest/java/edu/android/wut2eat/ui/favorites/FavoritesScreenTest.kt`, `testRendersNamesAndEmptyState`:
   `IllegalStateException: … has already set content` — the test calls `rule.setContent` twice. Call `setContent` once,
   driving the list from hoisted state: `var items by mutableStateOf<List<Shop>?>(emptyList())` declared in the test,
   `FavoritesScreen(items = items, …)` inside `setContent`; assert the empty state text; then
   `rule.runOnUiThread { items = listOf(shop1, shop2) }` (or plain assignment followed by `rule.waitForIdle()`), and
   assert both names are displayed. Keep the class at 2 tests.

Reply with the list of files you changed.
