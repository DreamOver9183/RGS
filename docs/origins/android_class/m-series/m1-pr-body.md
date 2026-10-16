## Summary

- **Dependencies:** add Navigation Compose 2.10.2 and kotlinx.serialization 1.11.0 (`org.jetbrains.kotlin.plugin.serialization`, tied to the Kotlin version). Add an R8 keep rule for the `@Serializable` routes in `ui.nav`.
- **App container:** `FoodRouletteApplication` lazily builds `di/AppContainer`, which owns the DataStore, location, Places search, API key state, and `viewModelFactory`. `MainActivity` gets the Activity-scoped `RouletteViewModel` from it, so Home state survives tab switches.
- **Single DataStore:** `data/AppDataStore.kt` declares the app's only `settings` Preferences DataStore. `DataStoreRadiusStore` now takes a `DataStore<Preferences>`, and existing radius settings are kept.
- **Navigation shell:** `ui/AppRoot.kt` (`FoodRouletteRoot`) adds a Scaffold with a bottom bar and a type-safe `NavHost`. `ui/nav/` holds `Routes.kt`, `TopLevelTab`, and `FoodBottomBar`. The tabs are 抽籤, 收藏, 多人, and 我的. The last three currently show `ui/common/PlaceholderScreen`. New heart, users, user, and back icons.
- **Home visibility:** `RouletteViewModel.onMapVisible()` is called from a `DisposableEffect` in `RouletteScreen`. While Home is off screen, it pauses the 15 s map-load timeout and suppresses vibration.
- **Tests:** JVM `RouletteViewModelVisibilityTest` (3) and `ui/nav/RoutesSerializationTest` (1). Instrumented `ui/nav/AppNavigationTest` (2) covers tab switching and a Home result surviving a tab round trip, using shared fakes in `testing/TestDoubles.kt`.
- **Docs:** AGENTS.md and README.md now cover the toolchain, structure, data flow, test counts, an "Add a screen" recipe, and troubleshooting.

Follows #1 (M0), which is already merged into `main`, so this diff contains only the three M1 commits.

## Test plan

- [x] `testDebugUnitTest`: 36 JVM tests in 9 classes, 0 failures
- [x] `lintDebug`: 0 errors (9 warnings, all version/target/config notices)
- [x] `assembleDebug`
- [x] `assembleRelease` (R8)
- [x] `connectedDebugAndroidTest` on a local API 37 emulator: 5 tests in 2 classes, 0 failures (`RouletteScreenTest` 3, `AppNavigationTest` 2)
- [ ] CI `build` job
- [ ] CI `instrumented` job

🤖 Generated with [Claude Code](https://claude.com/claude-code)
