# M7 review round 1 — fix exactly these points (same rules in gemini-rules.md; only these files; only inside the current workspace)

All in `app/src/androidTest/java/edu/android/wut2eat/ui/AppFlowTest.kt` unless stated otherwise. Background: several texts
exist on more than one page (e.g. `btn_draw_favorites` and `fav_draw_title` are both 從收藏抽; the booking page also shows
`demo_badge`; Home already shows the drawn shop's name), so a wait on such a text can pass before the navigation finished.
Every wait after a navigation must look for a node that exists ONLY on the target page.

1. `addShop_appearsInFavoritesAndDrawPool`, detail page: the detail page shows the shop name twice (top-bar title and body
   heading), so `rule.onNodeWithText("Test Noodle").performScrollTo().assertIsDisplayed()` fails with "found 2 nodes".
   Replace it with `rule.onAllNodesWithText("Test Noodle").assertCountEquals(2)` (import `assertCountEquals`) and keep the
   `demo_badge` assertion. Also make the wait before it require `btn_book` (only on the detail page) instead of `demo_badge`.
2. `addShop_appearsInFavoritesAndDrawPool`, after tapping `btn_draw_favorites` at the end: do not wait for `fav_draw_title`
   (same text as the button). Wait until `rule.onAllNodesWithText(string(R.string.fav_draw_count, 7)).fetchSemanticsNodes().isNotEmpty()`,
   then assert it with `performScrollTo().assertIsDisplayed()`.
3. `favoritesDraw_opensDetail_andBookingAppearsOnMe`:
   - after tapping `btn_done`: wait until `btn_book` exists AND `btn_done` no longer exists (back on the detail page);
   - after the first back: wait until `btn_draw_one` exists AND `btn_book` no longer exists (on the draw page);
   - after the second back: wait until `add_shop_short` exists AND `btn_draw_one` no longer exists (on the 收藏 tab — the
     新增 button is only in the 收藏 header);
   - after tapping the 我的 tab keep the `me_stat_bookings` wait.
4. `homeResult_shareSendsText`: after tapping the share icon, wait until `share_send` exists (only on the share page), not
   the shop name (Home already shows it). Replace `assertNotNull(text)` + `text!!` with `val text = checkNotNull(sharedText)`
   and remove the then-unused `assertNotNull` import.
5. `app/src/main/java/edu/android/wut2eat/ui/share/ShareScreen.kt`: remove the imports that became unused when the
   hand-made avatar circle was replaced (`androidx.compose.foundation.background`, `androidx.compose.foundation.shape.CircleShape`,
   `androidx.compose.ui.draw.clip`, and any other import no longer referenced in the file — check each one).

Reply with the list of files you changed.
