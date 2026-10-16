# Milestone M1 spec: bottom-navigation shell + app container

Read `gemini-rules.md` (same folder) first and follow it strictly. Read every existing file you modify in full
before editing it. Paths below are relative to the repo root; Kotlin sources live under
`app/src/main/java/edu/android/wut2eat/` (written `<main>/` below), JVM tests under
`app/src/test/java/edu/android/wut2eat/` (`<test>/`), instrumented tests under
`app/src/androidTest/java/edu/android/wut2eat/` (`<atest>/`).

Goal: the app gets a bottom navigation bar with 4 tabs (抽籤 / 收藏 / 多人 / 我的). 抽籤 hosts the existing
`RouletteScreen` unchanged in behaviour; the other three show a placeholder for now. Dependency wiring moves
out of `MainActivity` into an `AppContainer` owned by a new `Application` class. All existing tests must keep
passing without modification.

## 1. Build configuration (explicitly allowed in this milestone)

`gradle/libs.versions.toml` — add (keep the existing `agp = "9.3.0"` line exactly as is):
```toml
# [versions]
navigation = "2.10.2"
kotlinxSerialization = "1.11.0"
# [libraries]
androidx-navigation-compose = { group = "androidx.navigation", name = "navigation-compose", version.ref = "navigation" }
kotlinx-serialization-json = { group = "org.jetbrains.kotlinx", name = "kotlinx-serialization-json", version.ref = "kotlinxSerialization" }
# [plugins]
kotlin-serialization = { id = "org.jetbrains.kotlin.plugin.serialization", version.ref = "kotlin" }
```
Root `build.gradle.kts`: add `alias(libs.plugins.kotlin.serialization) apply false`.
`app/build.gradle.kts`: add `alias(libs.plugins.kotlin.serialization)` to `plugins {}`, and
`implementation(libs.androidx.navigation.compose)` + `implementation(libs.kotlinx.serialization.json)`
to dependencies (next to the other androidx / kotlinx lines). Change nothing else there.

`app/proguard-rules.pro`: append
```
# 導覽路由（type-safe navigation 以 kotlinx.serialization 序列化）
-keep @kotlinx.serialization.Serializable class edu.android.wut2eat.ui.nav.** { *; }
```

## 2. Single DataStore

New `<main>/data/AppDataStore.kt`:
```kotlin
package edu.android.wut2eat.data
/** 全 App 唯一的 Preferences DataStore（檔名沿用 "settings"，保留既有半徑設定）。同一檔案只能有一個 delegate。 */
val Context.appDataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")
```
Modify `<main>/data/SettingsStore.kt`: remove the private `settingsDataStore` delegate; change the class to
`class DataStoreRadiusStore(private val dataStore: DataStore<Preferences>) : RadiusStore` using
`dataStore.data.first()[RADIUS_KEY]` and `dataStore.edit { ... }`. Keep `RadiusStore` and `RADIUS_KEY` unchanged.
(Imports: `androidx.datastore.core.DataStore`, `androidx.datastore.preferences.core.Preferences`.)

## 3. Application + container

New `<main>/FoodRouletteApplication.kt`:
```kotlin
class FoodRouletteApplication : Application() {
    /** 依賴容器；第一次用到才建立（Places 初始化也延後到這時）。 */
    val container: AppContainer by lazy { AppContainer.create(this) }
}
```
Register it in `app/src/main/AndroidManifest.xml`: add `android:name=".FoodRouletteApplication"` to `<application>`.

New `<main>/di/AppContainer.kt` (package `edu.android.wut2eat.di`):
```kotlin
class AppContainer(
    val dataStore: DataStore<Preferences>,
    val location: LocationSource,
    val search: ShopSearch,
    val hasApiKey: Boolean,
    val isFatalError: (Throwable) -> Boolean,
) {
    val radiusStore: RadiusStore = DataStoreRadiusStore(dataStore)

    /** 建立所有 ViewModel 的 factory（目前只有 RouletteViewModel）。 */
    val viewModelFactory: ViewModelProvider.Factory = viewModelFactory {
        initializer {
            RouletteViewModel(
                radiusStore = radiusStore,
                location = location,
                search = search,
                hasApiKey = hasApiKey,
                isFatalError = isFatalError,
            )
        }
    }

    companion object {
        fun create(context: Context): AppContainer { /* moved from MainActivity, see below */ }
    }
}
```
`create`: use `val app = context.applicationContext`; move the API-key logic from `MainActivity`'s factory
verbatim (`BuildConfig.MAPS_API_KEY.trim()`, `PlacesSearch(app, apiKey)` + `placesSearch::search` when the key is
present, otherwise `{ _, _ -> emptyList() }`), `location = FusedLocationSource(app)`,
`dataStore = app.appDataStore`, `isFatalError = { PlacesSearch.isFatal(it) }`.
Imports for the DSL: `androidx.lifecycle.viewmodel.initializer`, `androidx.lifecycle.viewmodel.viewModelFactory`,
`androidx.lifecycle.ViewModelProvider`.

Modify `<main>/MainActivity.kt`:
- Replace the anonymous factory with
  `private val viewModel: RouletteViewModel by viewModels { (application as FoodRouletteApplication).container.viewModelFactory }`.
- Keep the permission logic and `openMapsUrl` exactly as they are.
- `setContent { FoodRouletteTheme { FoodRouletteRoot(rouletteViewModel = viewModel, onOpenMapsUrl = ::openMapsUrl, onReload = { viewModelStore.clear(); recreate() }) } }`
  (keep the existing Chinese comment about clearing the store above `onReload`).
- Remove imports that become unused.

## 4. RouletteViewModel: pause the map-load timeout while Home is hidden

In `<main>/ui/RouletteViewModel.kt` (additive change only; do not change any existing behaviour when the new
function is never called):
- Add `private var mapTimeoutJob: Job? = null` and `private var mapVisible = true`.
- Extract the timeout coroutine in `init` into `private fun startMapTimeout(): Job = viewModelScope.launch { delay(MAP_LOAD_TIMEOUT_MS); if (!mapReady && !_state.value.fatal) fail() }`
  and in `init` do `mapTimeoutJob = startMapTimeout()` where the old `launch` was.
- Add:
```kotlin
    /** Home 進出畫面（切換分頁）時呼叫：不在畫面上的地圖不會載入，暫停逾時計時；回到畫面時重新計時。 */
    fun onMapVisible(visible: Boolean) {
        mapVisible = visible
        if (mapReady || _state.value.fatal) return
        if (!visible) {
            mapTimeoutJob?.cancel()
            mapTimeoutJob = null
        } else if (mapTimeoutJob?.isActive != true) {
            mapTimeoutJob = startMapTimeout()
        }
    }
```
- In `spin()`, send `Effect.Vibrate` only when `mapVisible` is true (the shop result and `FitShop` are still
  emitted as today). Add `import kotlinx.coroutines.Job`.

In `<main>/ui/RouletteScreen.kt`, add right after the existing `LaunchedEffect(viewModel) { ... }` block:
```kotlin
    // 切到其他分頁時 Home 離開組成：通知 ViewModel 暫停地圖逾時、不補發震動
    DisposableEffect(viewModel) {
        viewModel.onMapVisible(true)
        onDispose { viewModel.onMapVisible(false) }
    }
```
(import `androidx.compose.runtime.DisposableEffect`). Do not change anything else in `RouletteScreen`.

## 5. Navigation

New `<main>/ui/nav/Routes.kt` (package `edu.android.wut2eat.ui.nav`):
```kotlin
@Serializable data object HomeRoute
@Serializable data object FavoritesRoute
@Serializable data object MultiplayerRoute
@Serializable data object MeRoute
```
(`import kotlinx.serialization.Serializable`; brief KDoc saying sub-page routes are added per milestone.)

New `<main>/ui/nav/TopLevelTab.kt`:
```kotlin
enum class TopLevelTab(val route: Any, @StringRes val label: Int, val icon: FoodIcon) {
    Home(HomeRoute, R.string.tab_home, FoodIcon.Dice),
    Favorites(FavoritesRoute, R.string.tab_favorites, FoodIcon.Heart),
    Multiplayer(MultiplayerRoute, R.string.tab_multi, FoodIcon.Users),
    Me(MeRoute, R.string.tab_me, FoodIcon.User),
}
```

New `<main>/ui/nav/FoodBottomBar.kt`:
`@Composable fun FoodBottomBar(currentDestination: NavDestination?, onSelect: (TopLevelTab) -> Unit, modifier: Modifier = Modifier)`
- Material3 `NavigationBar(containerColor = colors.sheet, modifier = modifier)` with one `NavigationBarItem` per
  `TopLevelTab.entries`.
- `selected = currentDestination?.hierarchy?.any { it.hasRoute(tab.route::class) } == true`
  (imports: `androidx.navigation.NavDestination`, `androidx.navigation.NavDestination.Companion.hasRoute`,
  `androidx.navigation.NavDestination.Companion.hierarchy`).
- icon: `Icon(painterResource(tab.icon.res), contentDescription = null, modifier = Modifier.size(24.dp))`;
  label: `Text(stringResource(tab.label))`.
- colors: `NavigationBarItemDefaults.colors(selectedIconColor = colors.accent, selectedTextColor = colors.accent,
  indicatorColor = colors.accent.copy(alpha = 0.14f), unselectedIconColor = colors.muted, unselectedTextColor = colors.muted)`
  where `colors = FoodTheme.colors`.

New `<main>/ui/AppRoot.kt` (package `edu.android.wut2eat.ui`):
```kotlin
@Composable
fun FoodRouletteRoot(
    rouletteViewModel: RouletteViewModel,
    onOpenMapsUrl: (String) -> Unit,
    modifier: Modifier = Modifier,
    onReload: () -> Unit = {},
)
```
- `val navController = rememberNavController()`;
  `val backStackEntry by navController.currentBackStackEntryAsState()`; `val dest = backStackEntry?.destination`.
- `val showBottomBar = TopLevelTab.entries.any { tab -> dest?.hierarchy?.any { it.hasRoute(tab.route::class) } == true }`
  (true before the first destination is known is fine either way; default to `true` when `dest == null`).
- `Scaffold(modifier = modifier, containerColor = FoodTheme.colors.mapBg, contentWindowInsets = WindowInsets(0), bottomBar = { if (showBottomBar) FoodBottomBar(dest, onSelect = { navController.navigateToTab(it) }) }) { inner -> NavHost(...) }`
- `NavHost(navController = navController, startDestination = HomeRoute, modifier = Modifier.fillMaxSize().padding(inner).consumeWindowInsets(inner))` with:
  - `composable<HomeRoute> { RouletteScreen(viewModel = rouletteViewModel, onOpenMapsUrl = onOpenMapsUrl, onReload = onReload) }`
  - `composable<FavoritesRoute> { PlaceholderScreen(R.string.tab_favorites) }`, same for `MultiplayerRoute`
    (`R.string.tab_multi`) and `MeRoute` (`R.string.tab_me`).
- Private extension in the same file:
```kotlin
private fun NavHostController.navigateToTab(tab: TopLevelTab) {
    navigate(tab.route) {
        popUpTo(graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}
```
Imports: `androidx.navigation.compose.NavHost`, `androidx.navigation.compose.composable`,
`androidx.navigation.compose.rememberNavController`, `androidx.navigation.compose.currentBackStackEntryAsState`,
`androidx.navigation.NavHostController`, `androidx.navigation.NavGraph.Companion.findStartDestination`,
`androidx.compose.foundation.layout.consumeWindowInsets`, `androidx.compose.foundation.layout.WindowInsets`.

New `<main>/ui/common/PlaceholderScreen.kt` (package `edu.android.wut2eat.ui.common`):
`@Composable fun PlaceholderScreen(@StringRes title: Int, modifier: Modifier = Modifier)` — full-size `Box` with
`colors.sheet` background, `statusBarsPadding()`, centered `Column`: `FoodIcon.Hourglass` icon (40.dp, tint
`colors.accent2`), title text (20.sp bold, `colors.ink`), and `R.string.coming_soon` (14.sp, `colors.muted`).

## 6. Icons and strings

New vector drawables in `app/src/main/res/drawable/` in the SAME hand-drawn style as `ic_dice.xml` / `ic_bowl.xml`
(24dp, viewport 24, `strokeColor="#FF000000"`, `strokeWidth="1.8"`, round caps/joins, slightly wobbly
hand-drawn paths, no fills except small dots): `ic_heart.xml` (heart outline), `ic_users.xml` (two people,
heads + shoulders), `ic_user.xml` (one person), `ic_back.xml` (left-pointing arrow/chevron). Add enum entries
`Heart`, `Users`, `User`, `Back` to `FoodIcon` in `<main>/ui/theme/Icons.kt`.

`app/src/main/res/values/strings.xml` — add:
`tab_home` 抽籤, `tab_favorites` 收藏, `tab_multi` 多人, `tab_me` 我的, `coming_soon` 即將推出.

## 7. Tests

JVM `<test>/ui/RouletteViewModelVisibilityTest.kt` (package `edu.android.wut2eat.ui`; REUSE the existing top-level
`FakeRadiusStore`, `FakeLocationSource`, `FakeShopSearch` from `RouletteViewModelTest.kt` — do not redeclare;
same dispatcher setup as `RouletteViewModelTest`), 3 tests:
1. `onMapVisible(false)` before the map loads → `advanceTimeBy(MAP_LOAD_TIMEOUT_MS + 1)` → not fatal, phase still Booting.
2. hide then show again → after `MAP_LOAD_TIMEOUT_MS + 1` from the show → fatal.
3. map loaded + startup done (phase Ready), then `onMapVisible(false)`, `spin()` with one shop, advance past
   `REEL_TIMEOUT_MS` → phase Result with the shop, and the collected effects contain no `Effect.Vibrate`
   (but do contain `Effect.FitShop`).

JVM `<test>/ui/nav/RoutesSerializationTest.kt`, 1 test: each of the 4 routes has a generated serializer whose
`descriptor.serialName` equals its fully qualified class name (e.g. `HomeRoute.serializer().descriptor.serialName == "edu.android.wut2eat.ui.nav.HomeRoute"`).

Instrumented `<atest>/testing/TestDoubles.kt` (package `edu.android.wut2eat.testing`): `class MemoryRadiusStore(var radius: Double = 3.0) : RadiusStore`
and `class FixedLocation(var pos: LatLon, var permissionGranted: Boolean = true) : LocationSource`.

Instrumented `<atest>/ui/nav/AppNavigationTest.kt` (package `edu.android.wut2eat.ui.nav`), modelled on the existing
`<atest>/ui/RouletteScreenTest.kt` (same rule `createAndroidComposeRule<ComponentActivity>()` from
`androidx.compose.ui.test.junit4.v2`, same `@After` closing the scenario, same `TIMEOUT_MS`), hosting
`FoodRouletteTheme { FoodRouletteRoot(rouletteViewModel = vm, onOpenMapsUrl = {}) }` with a `RouletteViewModel`
built from the test doubles; drive it to Ready with `vm.startup(); vm.onMapLoaded()` on the UI thread like the
existing test. 2 tests:
1. Tabs switch: clicking each tab label (`onNode(hasText(label) and isSelectable())`) makes that item
   `assertIsSelected()`, and the 收藏 tab shows `R.string.coming_soon`; clicking 抽籤 again shows the spin button
   (`R.string.btn_spin`).
2. Home result survives a tab round trip: spin with a one-shop search, wait for `Phase.Result`, switch to 收藏,
   switch back to 抽籤, and the result reel content description `getString(R.string.reel_result_desc, shop.name)`
   is displayed.

Do not modify `RouletteViewModelTest.kt` or `RouletteScreenTest.kt`.
