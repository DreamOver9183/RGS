# M2 review round 1 — please fix exactly these points (same rules as before: no git, no shell, no other files)

Builds and all 56 JVM tests pass — good work. Reviewer findings:

1. `app/src/main/java/edu/android/wut2eat/ui/Panel.kt`, result info row: the info `Text` (`parts.joinToString("・")`)
   has no weight, so with a long shop type/name it takes the whole row width and the heart `IconButton` and the
   「詳情」 `TextButton` get squeezed to zero width. Give that `Text` `Modifier.weight(1f, fill = false)` (keep
   `maxLines = 1` + ellipsis) so the buttons always keep their size. Keep the text exactly the same (tests look it up
   by text), and when both callbacks are null the layout must stay as before.
2. `app/src/main/java/edu/android/wut2eat/ui/detail/DetailScreen.kt`, 招牌菜 section: the three dish chips are in a
   single `Row` and overflow on narrow phones (dish names are up to 8 characters). Use a `FlowRow`
   (`androidx.compose.foundation.layout.FlowRow`, `@OptIn(ExperimentalLayoutApi::class)`) with 8.dp horizontal and
   vertical spacing instead.
3. `app/src/androidTest/java/edu/android/wut2eat/ui/nav/AppNavigationTest.kt`: remove the now-unused
   `MemoryRadiusStore` import.
4. Remove the extra trailing blank line you added at the end of: `ui/nav/Routes.kt`, `app/proguard-rules.pro`,
   `app/src/androidTest/java/edu/android/wut2eat/testing/TestDoubles.kt`, and
   `app/src/test/java/edu/android/wut2eat/domain/FormatTest.kt` (files should end with exactly one newline).

Reply with the list of files you changed.
