# Rules for the implementing agent (Gemini)

You are implementing one milestone of the Android app in the current workspace
(package `edu.android.wut2eat`). The repo root is the directory this agy session was started in — it may be the
main checkout or a separate git worktree of the same project.
A separate reviewer (Claude) will review your diff and run all builds/tests.

Hard rules:
0. Only read and write files under the CURRENT workspace directory. Never write to any other checkout of the project
   (e.g. never `<repo>` when you were started in `<repo>-m4fix`), even if
   an earlier turn of this conversation worked there. Resolve every path relative to the current workspace.
1. Only create/modify the files the milestone spec lists (or clearly implies). Do not touch anything else.
2. Never run git commands (no add/commit/branch/stash/checkout/reset). Never push.
3. Never open, read, print, or modify `local.properties`. It contains a secret API key.
4. Do not modify `AGENTS.md` or `README.md`; the reviewer maintains documentation.
5. Do not change dependency versions, plugins, Gradle settings, or CI unless the spec explicitly says so.
6. You cannot run shell commands in this session; do not try. Write code that compiles: double-check imports,
   signatures, and named arguments against the existing source files before using them.
7. Match the surrounding code style: Kotlin official style, 4-space indent, trailing commas in multi-line
   parameter lists, Traditional Chinese for user-visible strings (always in `res/values/strings.xml`, never
   hardcoded in Kotlin), short Chinese KDoc/comments in the same density as existing files.
8. Keep `domain/` pure Kotlin (no Android or Google SDK imports).
9. Tests: JUnit4 + `org.junit.Assert`, `kotlinx-coroutines-test` (`runTest`, `StandardTestDispatcher`,
   `Dispatchers.setMain/resetMain`). No new test libraries. Do not redeclare `FakeRadiusStore`,
   `FakeLocationSource`, or `FakeShopSearch` in package `edu.android.wut2eat.ui` (they already exist in
   `app/src/test/java/edu/android/wut2eat/ui/RouletteViewModelTest.kt`).
10. When finished, print a short summary: every file you created/modified, and anything in the spec you could
    not do or were unsure about. Do not claim you ran or passed any test.
