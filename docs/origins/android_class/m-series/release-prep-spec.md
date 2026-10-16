# Release prep v1.0.0 — make exactly these edits (rules in gemini-rules.md apply; this spec explicitly allows the one build-file change below)

1. `app/build.gradle.kts`, `defaultConfig`: `versionCode = 1` → `versionCode = 2`, and `versionName = "0.1.0"` →
   `versionName = "1.0.0"`. Change nothing else in the file.
2. `app/src/main/java/edu/android/wut2eat/ui/nav/Routes.kt`: the file comment says sub-page routes are added
   milestone by milestone (「子頁面路由依里程碑逐步加入」), which is stale now that all routes exist. Replace that comment
   with a short accurate Chinese comment, e.g. 「底部分頁與子頁面的 type-safe 導覽路由；子頁面只帶 shop id 等基本型別參數」.
3. `app/src/androidTest/java/edu/android/wut2eat/ui/nav/AppNavigationTest.kt` (≈ line 96): the KDoc of `testTabsSwitch`
   still says 預留頁顯示「即將推出」 — there are no placeholder pages any more. Reword it to describe what the test checks now
   (each tab is selected and shows its real content: the 收藏 list, the 多人 player buttons, the 我的 default name, and Home's
   spin button on return). Comment only; do not change any code.

Every file keeps exactly one trailing newline. Reply with the list of files you changed.
