# Milestone M4 spec: 我的 tab (fake user profile) + fake/custom location override

Read `gemini-rules.md` (same folder) first and follow it strictly. Read every existing file you modify in full
first, and the code you build on: `ui/RouletteViewModel.kt`, `ui/RouletteHooks.kt`, `ui/RouletteScreen.kt`,
`ui/MapLayer.kt` (GoogleMap usage), `ui/AppRoot.kt`, `di/AppContainer.kt`, `data/*.kt`, `data/store/StoreCodec.kt`,
`ui/common/*`, `ui/favorites/*`, `ui/theme/Theme.kt`, and test helpers under `<test>/testing/` and
`<test>/ui/RouletteViewModelTest.kt` (public `FakeRadiusStore`, `FakeLocationSource`, `FakeShopSearch`).
Shorthands: `<main>/` = `app/src/main/java/edu/android/wut2eat/`, `<test>/`, `<atest>/`, `<res>/` as before.
Conventions as in M2/M3 (ViewModel with plain args, stateless `XxxScreen`, stateful `XxxPage`). All text in
`strings.xml`. No new dependencies (`maps-compose` is already available for the map picker).

## 1. Domain (pure Kotlin)

New `<main>/domain/FakeLocation.kt`:
```kotlin
/** 假定位設定；label 空白表示地圖選點（UI 以座標顯示） */
data class FakeLocation(val enabled: Boolean = false, val pos: LatLon = FALLBACK_POS, val label: String = "")
data class PresetPlace(val name: String, val pos: LatLon)
val PRESET_PLACES: List<PresetPlace>  // 台中車站 = FALLBACK_POS, 台北車站 (25.0478, 121.5170),
                                      // 新竹車站 (24.8016, 120.9716), 台南車站 (22.9971, 120.2128), 高雄車站 (22.6394, 120.3022)
```
New `<main>/domain/Profile.kt`:
```kotlin
const val MAX_NICKNAME = 16
const val AVATAR_COUNT = 6
data class Profile(val nickname: String = "", val avatar: Int = 0)
/** 去頭尾空白並截到 MAX_NICKNAME 個字元 */
fun normalizeNickname(raw: String): String
```

## 2. Data

1. `<main>/data/store/StoreCodec.kt`: add
   `@Serializable data class StoredFakeLocation(val enabled: Boolean = false, val lat: Double, val lon: Double, val label: String = "")`
   and `@Serializable data class StoredProfile(val nickname: String = "", val avatar: Int = 0)` with
   `encodeFakeLocation/decodeFakeLocation(raw: String?): FakeLocation` and `encodeProfile/decodeProfile(raw: String?): Profile`
   (null/blank/corrupt → the default `FakeLocation()` / `Profile()`; avatar coerced into `0 until AVATAR_COUNT`).
2. New `<main>/data/FakeLocationRepository.kt`:
   `interface FakeLocationRepository { val setting: Flow<FakeLocation>; suspend fun save(value: FakeLocation) }` and
   `class DataStoreFakeLocationRepository(dataStore)` with key `stringPreferencesKey("fake_location_v1")`.
3. New `<main>/data/ProfileRepository.kt`:
   `interface ProfileRepository { val profile: Flow<Profile>; suspend fun save(value: Profile) }` and
   `class DataStoreProfileRepository(dataStore)` with key `stringPreferencesKey("profile_v1")`.
   (Both: same IOException `catch` + `distinctUntilChanged()` pattern as `DataStoreFavoritesRepository`.)
4. New `<main>/data/OverridableLocationSource.kt`:
   ```kotlin
   /** 假定位開啟時以它取代 GPS：current() 回傳假位置；hasPermission() 視為已授權 */
   class OverridableLocationSource(
       private val real: LocationSource,
       private val state: StateFlow<FakeLocation>,     // for the synchronous hasPermission()
       private val setting: Flow<FakeLocation>,        // read fresh in current()
   ) : LocationSource {
       override fun hasPermission(): Boolean = state.value.enabled || real.hasPermission()
       override suspend fun current(): LatLon { val f = setting.first(); return if (f.enabled) f.pos else real.current() }
   }
   ```
5. `AppContainer`:
   - `val fakeLocation: FakeLocationRepository = DataStoreFakeLocationRepository(dataStore)`,
     `val profile: ProfileRepository = DataStoreProfileRepository(dataStore)`.
   - `val fakeLocationState: StateFlow<FakeLocation> = fakeLocation.setting.stateIn(appScope, SharingStarted.Eagerly, FakeLocation())`.
   - `val effectiveLocation: LocationSource = OverridableLocationSource(location, fakeLocationState, fakeLocation.setting)`.
   - `RouletteViewModel` initializer: `location = effectiveLocation` and add `fakeLocation = fakeLocation.setting` to its hooks.
   - Initializers: `MeViewModel(profile, favorites, stats, fakeLocation)` and `FakeLocationViewModel(fakeLocation, baseLocation = location)`.

## 3. RouletteViewModel: react to fake-location changes (additive; existing tests unchanged)

- `RouletteHooks`: add `val fakeLocation: Flow<FakeLocation> = emptyFlow()`.
- `UiState`: add `val fakeLabel: String? = null` — non-null while the fake location is enabled: its `label`, or `""` for a
  map-picked point (UI formats coordinates).
- `init` (both branches): launch a collector of `hooks.fakeLocation.distinctUntilChanged()`; the FIRST emission only sets
  `fakeLabel` (startup already uses the decorated location source); every later emission calls `onFakeLocation(f)`.
- `private fun onFakeLocation(f: FakeLocation)`: set `fakeLabel`; if a spin is in progress, store it in
  `private var pendingFake: FakeLocation?` and return; otherwise:
  - enabled → `_state.update { it.copy(geoOk = true, toastDismissed = true, userPicked = true) }` then `moveTo(f.pos, pan = true)`;
  - disabled → if `location.hasPermission()` then `doLocate()` else `setGeoFailed()`.
- At the end of the `spin()` coroutine (every exit path: result, empty, error), apply a pending change:
  `pendingFake?.let { pendingFake = null; onFakeLocation(it) }` (use `try { … } finally { … }` around the body).

`RouletteScreen`: new trailing param `onOpenFakeLocation: (() -> Unit)? = null`. When `state.fakeLabel != null`, show a
chip centered under the top row (same `Surface(CircleShape)` style as the geo toast but `colors.me` border):
`FoodIcon.Pin` + `stringResource(R.string.fake_chip, label)` where label = `fakeLabel.ifBlank { stringResource(R.string.fake_map_point, pos.lat, pos.lon) }`;
clickable → `onOpenFakeLocation` when non-null. Hide the geo toast while the chip is shown. In `AppRoot.kt` pass
`onOpenFakeLocation = { navController.navigate(FakeLocationRoute) }` for Home.

## 4. Shared UI

1. `<main>/ui/theme/Theme.kt`: add `val AvatarColors: List<Color>` with exactly `AVATAR_COUNT` (6) pleasant colours
   (e.g. 0xFFE4572E, 0xFFD98A1C, 0xFF2A7DE1, 0xFF3BA776, 0xFF8E5BD8, 0xFFE0607E).
2. New `<main>/ui/common/Avatar.kt`: `@Composable fun Avatar(nickname: String, colorIndex: Int, modifier: Modifier = Modifier, size: Dp = 64.dp)`
   — circle in `AvatarColors[colorIndex.coerceIn(…)]` with the first character of the nickname (or `R.string.me_default_initial`)
   in white bold, font ≈ size × 0.42.
3. New `<main>/ui/common/LocationPicker.kt`:
   ```kotlin
   @Composable
   fun LocationPicker(
       selected: LatLon,
       onPickMap: (LatLon) -> Unit,
       onPickPreset: (PresetPlace) -> Unit,
       modifier: Modifier = Modifier,
       onUseCurrent: (() -> Unit)? = null,
       mapHeight: Dp = 220.dp,
   )
   ```
   - A `GoogleMap` (maps-compose) of `mapHeight`, 12.dp rounded clip, `contentDescription = stringResource(R.string.picker_map_desc)`,
     same `MapUiSettings` flags as `MapLayer`, a `Marker`/`MarkerComposable` at `selected`, `onMapClick` →
     `onPickMap(LatLon(it.latitude, wrapLon(it.longitude)))`, `onMapLoaded` sets a local `loaded` flag.
   - Keep the camera on the selection: `LaunchedEffect(selected) { cameraState.position = CameraPosition.fromLatLngZoom(selected.toLatLng(), 14f) }`
     (direct assignment, no animation — safe before the map loads).
   - If the map has not loaded after 10 s, show `R.string.picker_map_unavailable` (13.sp `colors.accent2`) under the map.
   - Below: a `FlowRow` (`@OptIn(ExperimentalLayoutApi::class)`) of `FilterChip`s, one per `PRESET_PLACES` entry
     (`selected` when `distanceKm(selected, preset.pos) < 0.01`), plus a chip `R.string.picker_use_current` when
     `onUseCurrent != null`.

## 5. Fake location page — package `edu.android.wut2eat.ui.location`

```kotlin
data class FakeLocationUiState(val setting: FakeLocation? = null, val locating: Boolean = false, val locateFailed: Boolean = false)
class FakeLocationViewModel(private val repo: FakeLocationRepository, private val baseLocation: LocationSource) : ViewModel() {
    val state: StateFlow<FakeLocationUiState>
    fun setEnabled(enabled: Boolean)          // keeps pos/label
    fun pickPreset(preset: PresetPlace)       // saves enabled = true, pos, label = preset.name
    fun pickOnMap(pos: LatLon)                // saves enabled = true, pos, label = ""
    fun useCurrent()                          // baseLocation.current() → enabled = true, pos, label = ""; failure → locateFailed = true
}
```
Writes go through `repo.save` in `viewModelScope`; `state` combines `repo.setting` with local `locating`/`locateFailed`
flags (`stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), FakeLocationUiState())`). Rethrow `CancellationException`.

`FakeLocationScreen(state: FakeLocationUiState, onBack: () -> Unit, onToggle: (Boolean) -> Unit, onPickPreset: (PresetPlace) -> Unit, onPickMap: (LatLon) -> Unit, onUseCurrent: () -> Unit, modifier: Modifier = Modifier)`
inside `SubPageScaffold(title = stringResource(R.string.fake_title), onBack)`, scrollable, 16.dp padding:
1. A row: text `R.string.fake_switch` + `Switch(checked = setting.enabled, onCheckedChange = onToggle)` (Switch gets
   `Modifier.semantics { contentDescription = <fake_switch text> }`); disabled while `setting == null`.
2. Current value: `stringResource(R.string.fake_current, label)` (label or formatted coordinates via `R.string.fake_map_point`).
3. Explanation `R.string.fake_explain` (13.sp muted). `R.string.fake_locate_failed` when `locateFailed`.
4. `LocationPicker(selected = setting?.pos ?: FALLBACK_POS, onPickMap, onPickPreset, onUseCurrent = onUseCurrent)`.
`FakeLocationPage(onBack: () -> Unit, modifier: Modifier = Modifier)`.

Navigation: `@Serializable data object FakeLocationRoute` in `Routes.kt`; `composable<FakeLocationRoute>` in `AppRoot.kt`.

## 6. Me tab — package `edu.android.wut2eat.ui.me`

```kotlin
data class MeUiState(val profile: Profile? = null, val favoritesCount: Int = 0, val drawCount: Int = 0, val fake: FakeLocation = FakeLocation())
class MeViewModel(
    private val profile: ProfileRepository,
    favorites: FavoritesRepository,
    stats: StatsRepository,
    fakeLocation: FakeLocationRepository,
) : ViewModel() {
    val state: StateFlow<MeUiState>   // combine of the four flows, stateIn(WhileSubscribed(5_000), MeUiState())
    fun saveNickname(raw: String)     // normalizeNickname, keep avatar
    fun setAvatar(index: Int)         // coerce into 0 until AVATAR_COUNT, keep nickname
}
```
`MeScreen(state: MeUiState, onSaveNickname: (String) -> Unit, onSetAvatar: (Int) -> Unit, onOpenFakeLocation: () -> Unit, modifier: Modifier = Modifier, onOpenAddShop: (() -> Unit)? = null)`
— top-level tab page (no back), `colors.sheet` background, `statusBarsPadding()`, scrollable, 16.dp padding:
1. Title `R.string.tab_me` (22.sp bold).
2. Profile card: `Avatar(nickname, avatar, size = 72.dp)`, display name (nickname or `R.string.me_default_name`), a row
   of `AVATAR_COUNT` 32.dp colour circles (selected one has a 3.dp `colors.ink` ring; each has contentDescription
   `stringResource(R.string.me_avatar_desc, i + 1)`) → `onSetAvatar(i)`.
3. Nickname editor: `OutlinedTextField` (label `R.string.me_nickname_label`, single line, local `rememberSaveable` text
   initialised from the profile; supporting text `R.string.me_nickname_hint` with the max length) + a `TextButton`
   `R.string.btn_save` → `onSaveNickname(text)`.
4. Stats row of two cards: `R.string.me_stat_favorites` / `favoritesCount`, `R.string.me_stat_draws` / `drawCount`.
5. Settings list: a row `R.string.fake_title` with the status text (`R.string.me_fake_on` with the label or
   `R.string.me_fake_off`) → `onOpenFakeLocation`; a row `R.string.add_shop_title` → `onOpenAddShop` only when non-null.
`MePage(onOpenFakeLocation: () -> Unit, modifier: Modifier = Modifier, onOpenAddShop: (() -> Unit)? = null)`; in `AppRoot.kt`
replace the `MeRoute` placeholder with `MePage(onOpenFakeLocation = { navController.navigate(FakeLocationRoute) })`.
If `PlaceholderScreen` is no longer used anywhere, delete it and the `coming_soon` string, and update
`<atest>/ui/nav/AppNavigationTest.kt` as described in section 9 item 3.

## 7. Strings
`fake_title` 自訂定位, `fake_switch` 使用假定位, `fake_current` 目前假定位：%1$s, `fake_map_point` 地圖選點（%1$.4f, %2$.4f）,
`fake_explain` 開啟後，主頁與多人抽都會以這個位置取代 GPS；關閉後回到真實定位。, `fake_locate_failed` 目前無法取得真實定位,
`fake_chip` 假定位：%1$s, `picker_map_desc` 選擇位置的地圖, `picker_map_unavailable` 地圖暫時無法載入，可以改用下方的預設地點,
`picker_use_current` 目前位置, `me_default_name` 美食探險家, `me_default_initial` 食, `me_avatar_desc` 頭像顏色 %1$d,
`me_nickname_label` 暱稱, `me_nickname_hint` 最多 %1$d 個字, `btn_save` 儲存, `me_stat_favorites` 收藏,
`me_stat_draws` 抽籤次數, `me_fake_on` 開啟：%1$s, `me_fake_off` 關閉, `add_shop_title` 新增餐廳.

## 8. Tests

JVM:
- `<test>/domain/PresetsTest.kt` (1): 5 presets, unique names, the first equals `FALLBACK_POS`, all inside Taiwan
  (lat 21.8–25.4, lon 119.9–122.1); also `normalizeNickname("  abcdefghijklmnopqrst ") == "abcdefghijklmnop"`.
- `<test>/data/OverridableLocationSourceTest.kt` (3): disabled → delegates to the real source; enabled → returns the
  fake pos without calling the real source; `hasPermission()` true when enabled even if the real source has none.
  (Use `FakeLocationSource` from `edu.android.wut2eat.ui` and a `MutableStateFlow<FakeLocation>` for both params.)
- `<test>/data/DataStoreProfileAndFakeLocationTest.kt` (2): real DataStore (same setup as the favorites repository test);
  profile and fake-location round trips, defaults when empty.
- `<test>/ui/RouletteFakeLocationTest.kt` (4, package `edu.android.wut2eat.ui`, `MutableSharedFlow`/`MutableStateFlow` as
  `hooks.fakeLocation`): (1) the first emission only sets `fakeLabel`, `pos` unchanged; (2) a later enabled emission moves
  `pos`, emits `Effect.PanTo`, sets `userPicked` and `fakeLabel`; (3) a later disabled emission with permission calls the
  location source again and clears `fakeLabel`; (4) a change during a spin is applied only after the result is shown.
- `<test>/ui/me/MeViewModelTest.kt` (3): combines counts/profile/fake; `saveNickname` normalises; `setAvatar` clamps.
  Add in-memory fakes `FakeProfileRepository`, `FakeFakeLocationRepository`, `FakeStatsRepository` to `<test>/testing/`.
- `<test>/ui/location/FakeLocationViewModelTest.kt` (3): `pickPreset` saves enabled + label; `setEnabled(false)` keeps the
  position; `useCurrent` failure sets `locateFailed`.

Instrumented (stateless screens):
- `<atest>/ui/me/MeScreenTest.kt` (2): shows nickname, both stat values, and the fake-location status; typing a nickname
  and pressing `btn_save` calls `onSaveNickname` with it; clicking the fake-location row calls `onOpenFakeLocation`.
- `<atest>/ui/location/FakeLocationScreenTest.kt` (2): clicking the 台北車站 chip calls `onPickPreset` with that preset;
  the switch calls `onToggle(true)` when off. (The map may not load without a key — tests use the chips/switch only.)

## 9. Carry-over fixes from the PR #3 merge-gate review (do these too)

1. Double-tap navigation guard (`<main>/ui/AppRoot.kt`): rapid double taps currently push two identical sub-pages, and
   a second back tap during the exit animation can pop the start destination. For every `navController.navigate(...)`
   to a sub-page route pass `{ launchSingleTop = true }`, and only act when the calling entry is resumed: inside each
   `composable<…> { entry -> … }` wrap callbacks so they check
   `entry.lifecycle.currentState == Lifecycle.State.RESUMED` before navigating or popping (a small private helper such as
   `fun NavBackStackEntry.ifResumed(block: () -> Unit)` is fine). Back actions use `navController.popBackStack()` guarded
   the same way.
2. Test container hygiene (`<atest>/testing/TestDoubles.kt`): `testContainer(...)` gets a `scope: CoroutineScope`
   parameter used both as the DataStore scope (`PreferenceDataStoreFactory.create(scope = scope, produceFile = …)`) and as
   the container's `appScope`; DataStore files go to `File(context.cacheDir, "test-datastores/test-<uuid>.preferences_pb")`.
   Add `fun clearTestDataStores(context: Context)` that deletes that directory. Every test using `testContainer` creates
   `CoroutineScope(SupervisorJob() + Dispatchers.IO)`, and in `@After` cancels it and calls `clearTestDataStores`.
3. `<atest>/ui/nav/AppNavigationTest.kt` `testTabsSwitch`: M3 already asserts the 收藏 tab (seeded shop) and the 多人 tab
   (`multi_draw_player` 1). Now that 我的 becomes a real page, replace its `coming_soon` assertion with the 我的 page
   content (e.g. the `me_default_name` text), and remove `coming_soon`/`PlaceholderScreen` if nothing uses them anymore.
