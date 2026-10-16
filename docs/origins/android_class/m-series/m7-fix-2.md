# M7 review round 2 — fix exactly these points (same rules in gemini-rules.md; only these files; only inside the current workspace)

1. `app/src/androidTest/java/edu/android/wut2eat/ui/AppFlowTest.kt`, test `favoritesDraw_opensDetail_andBookingAppearsOnMe`
   fails on the device with a `ComposeTimeoutException` at the wait after the FIRST back (≈ line 152). Reason (my mistake in
   round 1): when you come back to the favorites-draw page it still shows its result, and in the result state the draw
   button reads `btn_spin_again` (再拉一次), not `btn_draw_one`, so "btn_draw_one exists" never becomes true.
   Fix the two waits:
   - after the first back (detail → draw page): wait until
     `rule.onAllNodesWithText(string(R.string.fav_draw_count, 6)).fetchSemanticsNodes().isNotEmpty()` (the 6 seed shops;
     this count text is only on the draw page) AND `btn_book` no longer exists;
   - after the second back (draw page → 收藏 tab): wait until `add_shop_short` exists AND the `fav_draw_count` (6) text no
     longer exists.
   Leave everything else in the test as it is.

2. `app/src/main/java/edu/android/wut2eat/ui/theme/Theme.kt`: unselected `FilterChip` borders still use Material's
   default lavender-grey outline. In both colour schemes also pass `outlineVariant`:
   light `Color(0xFFE5D9CC)`, dark `Color(0xFF4A4360)`. Nothing else.

3. `app/proguard-rules.pro` (the spec explicitly allows this one build file): the R8 configuration analyzer reports that
   the `data.store` rule is fully subsumed by kotlinx.serialization's own consumer rules (its `serializer(...)` part
   matches nothing, and its `Companion` part duplicates `-keepclassmembers @kotlinx.serialization.Serializable class ** { static ** Companion; }`).
   Delete that rule AND its comment line (`# DataStore 內的 JSON（kotlinx.serialization）`), plus the blank line before it,
   so the file ends right after the navigation-route rule with exactly one newline. Keep the other two rules and their
   comments exactly as they are.

Reply with the list of files you changed.
