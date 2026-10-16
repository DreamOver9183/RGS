# Milestone M2 spec: favorites tab, restaurant detail page, seeded demo shops, Home result actions

Read `gemini-rules.md` (same folder) first and follow it strictly. Read every existing file you modify in full
first, and read the M1 code you build on (`di/AppContainer.kt`, `ui/AppRoot.kt`, `ui/nav/*`,
`ui/common/PlaceholderScreen.kt`, `data/AppDataStore.kt`, `data/SettingsStore.kt`). Path shorthands:
`<main>/` = `app/src/main/java/edu/android/wut2eat/`, `<test>/` = `app/src/test/java/edu/android/wut2eat/`,
`<atest>/` = `app/src/androidTest/java/edu/android/wut2eat/`, `<res>/` = `app/src/main/res/`.

Naming convention for every new screen package: `XxxViewModel` (state + logic, plain constructor params, never
calls `toRoute()`), stateless `XxxScreen(state, callbacks..., modifier)` (what UI tests render), and a stateful
`XxxPage(...)` composable that obtains the ViewModel with `viewModel(factory = LocalAppContainer.current.viewModelFactory)`
and wires it to `XxxScreen`. (Do not name composables `XxxRoute` — that suffix is used by navigation route objects.)

All user-visible text goes to `<res>/values/strings.xml` (Traditional Chinese). No new dependencies.

## 1. Domain (pure Kotlin, package `edu.android.wut2eat.domain`)

1. `Shop` (`<main>/domain/Places.kt`): add a trailing property `val note: String = ""` (after `distKm`; KDoc:
   自訂餐廳的地址／備註). Nothing else changes.
2. New `<main>/domain/ShopIds.kt`:
   ```kotlin
   const val CUSTOM_ID_PREFIX = "custom:"
   const val SEED_ID_PREFIX = "seed:"
   /** Places 的店才有 place id；自訂與示範店沒有 */
   val Shop.isPlacesShop: Boolean get() = !id.startsWith(CUSTOM_ID_PREFIX) && !id.startsWith(SEED_ID_PREFIX)
   ```
3. `<main>/domain/Format.kt` `mapsUrl(shop)`: keep the current URL for `shop.isPlacesShop`; otherwise return
   `"https://www.google.com/maps/search/?api=1&query=" + String.format(Locale.US, "%.6f,%.6f", shop.lat, shop.lon)`.
4. New `<main>/domain/Area.kt`: `data class SearchArea(val center: LatLon, val radiusKm: Double)` (KDoc: 主頁目前的搜尋中心與半徑).
5. New `<main>/domain/Extras.kt` — deterministic fake supplementary data per shop id:
   ```kotlin
   const val FAKE_INTRO_COUNT = 8
   const val FAKE_DISH_COUNT = 16
   data class ShopExtras(
       val rating: Double,          // 3.5..4.9, one decimal
       val reviews: Int,            // 12..2400
       val priceLevel: Int,         // 1..4
       val openMinute: Int,         // minutes after midnight, one of 600, 660, 690, 1020
       val closeMinute: Int,        // one of 1260, 1320, 1380
       val closedWeekday: Int?,     // ISO day 1(Mon)..7(Sun), or null = 全年無休
       val introIndex: Int,         // 0 until FAKE_INTRO_COUNT
       val dishIndices: List<Int>,  // 3 distinct values in 0 until FAKE_DISH_COUNT
   )
   fun fakeExtras(id: String): ShopExtras  // kotlin.random.Random(id.hashCode()); same id → same result
   fun formatClock(minute: Int): String     // "%02d:%02d" with Locale.US, e.g. 690 → "11:30"
   ```
   `closedWeekday`: draw `nextInt(10)`; values 1..7 map to that weekday, anything else → null.
6. New `<main>/domain/Seed.kt`: `val SEED_SHOPS: List<Shop>` — exactly 6 fictional shops (do not use real brand
   names) within 1.5 km of `FALLBACK_POS` (Taichung Station 24.1369, 120.685), ids `seed:01` … `seed:06`, status
   `STATUS_OPERATIONAL`, `type` a Chinese display type. Use these: 綠川拉麵屋 (拉麵店), 車站後街小吃 (小吃店),
   老樹下咖哩 (咖哩餐廳), 巷口滷肉飯 (台式料理), 雙十路燒肉 (燒肉餐廳), 小巷甜湯 (甜品店); pick plausible distinct
   coordinates (offsets of ±0.003..0.012 degrees).

## 2. Data

1. New `<main>/data/store/StoreCodec.kt` (package `edu.android.wut2eat.data.store`):
   ```kotlin
   internal val StoreJson = Json { ignoreUnknownKeys = true; encodeDefaults = true }
   @Serializable data class StoredShop(val id: String, val name: String, val lat: Double, val lon: Double,
       val status: String? = null, val type: String = "", val note: String = "")
   fun Shop.toStored(): StoredShop      // drops distKm (session-relative)
   fun StoredShop.toShop(): Shop
   fun encodeShops(shops: List<Shop>): String   // StoreJson.encodeToString(ListSerializer(StoredShop.serializer()), …)
   fun decodeShops(raw: String?): List<Shop>    // null/blank/corrupt (SerializationException or IllegalArgumentException) → emptyList()
   ```
2. New `<main>/data/FavoritesRepository.kt`:
   ```kotlin
   interface FavoritesRepository {
       /** 最新加入的在最前面 */
       val favorites: Flow<List<Shop>>
       suspend fun add(shop: Shop)          // no duplicates by id; new ones go first
       suspend fun remove(id: String)
       suspend fun toggle(shop: Shop): Boolean  // returns true if the shop is a favorite afterwards
       /** 第一次啟動時放入示範收藏；只做一次（使用者全刪後不會再出現） */
       suspend fun seedIfFirstRun()
   }
   class DataStoreFavoritesRepository(private val dataStore: DataStore<Preferences>) : FavoritesRepository
   ```
   Keys: `stringPreferencesKey("favorites_v1")`, `booleanPreferencesKey("seeded_v1")`. Every mutation is one
   `dataStore.edit { }` (read-modify-write inside the block). `seedIfFirstRun`: in ONE edit, if `seeded_v1` is not
   true → favorites = existing + SEED_SHOPS not already present (by id), then set `seeded_v1 = true`.
   `favorites` = `dataStore.data.catch { if (it is IOException) emit(emptyPreferences()) else throw it }.map { decodeShops(it[KEY]) }.distinctUntilChanged()`.
3. New `<main>/data/Session.kt`:
   ```kotlin
   /** 行程內共用暫存：主頁目前的搜尋區域、抽過的店（供簡介／分享／預訂頁以 id 查回）。 */
   class Session {
       val area = MutableStateFlow(SearchArea(FALLBACK_POS, DEFAULT_RADIUS_KM))
       val registry = ShopRegistry()
   }
   /** 最近抽到的店（LRU，預設 200 筆），執行緒安全 */
   class ShopRegistry(private val capacity: Int = 200) {
       fun put(shop: Shop)
       fun get(id: String): Shop?
   }
   ```
   (Implement with an access-ordered `LinkedHashMap` guarded by `@Synchronized`; evict eldest above capacity.)
4. New `<main>/data/ShopLookup.kt`:
   ```kotlin
   /** 以 id 找店：抽過的店 → 收藏 → 示範店。之後的里程碑會再加入自訂餐廳與預訂快照。 */
   class ShopLookup(private val registry: ShopRegistry, private val favorites: FavoritesRepository) {
       suspend fun find(id: String): Shop?
   }
   ```
5. `app/proguard-rules.pro`: append
   ```
   # DataStore 內的 JSON（kotlinx.serialization）
   -keepclassmembers @kotlinx.serialization.Serializable class edu.android.wut2eat.data.store.** { *** Companion; kotlinx.serialization.KSerializer serializer(...); }
   ```

## 3. RouletteViewModel hooks (additive; existing tests must pass unchanged)

New `<main>/ui/RouletteHooks.kt`:
```kotlin
/** 主頁與其他頁共用狀態的接點；預設全部不做事，測試不需提供。 */
class RouletteHooks(
    val onAreaChanged: (SearchArea) -> Unit = {},
    val onDrawn: (Shop) -> Unit = {},
)
```
`RouletteViewModel`: add a LAST constructor parameter `private val hooks: RouletteHooks = RouletteHooks()`.
- In `init` (both branches, i.e. regardless of `hasApiKey`), launch
  `_state.map { SearchArea(it.pos, it.radius) }.distinctUntilChanged().collect { hooks.onAreaChanged(it) }`
  in `viewModelScope`.
- In `spin()`, right after the state is updated to `Phase.Result` with the chosen shop, call `hooks.onDrawn(got.chosen)`.

## 4. Container and composition local

`<main>/di/AppContainer.kt`:
- Add constructor param (last) `appScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)`.
- Add `val session = Session()`, `val favorites: FavoritesRepository = DataStoreFavoritesRepository(dataStore)`,
  `val shopLookup = ShopLookup(session.registry, favorites)`, and `init { appScope.launch { favorites.seedIfFirstRun() } }`.
- `RouletteViewModel` initializer passes `hooks = RouletteHooks(onAreaChanged = { session.area.value = it }, onDrawn = { session.registry.put(it) })`.
- Add initializers:
  - `FavoritesViewModel(favorites, session.area)`
  - `DetailViewModel(shopId = createSavedStateHandle().toRoute<DetailRoute>().shopId, lookup = shopLookup, favorites = favorites, area = session.area)`
    (imports `androidx.lifecycle.createSavedStateHandle`, `androidx.navigation.toRoute`).
New `<main>/di/LocalAppContainer.kt`: `val LocalAppContainer = staticCompositionLocalOf<AppContainer> { error("AppContainer not provided") }`.

## 5. Navigation

- `<main>/ui/nav/Routes.kt`: add `@Serializable data class DetailRoute(val shopId: String)`.
- `<main>/ui/AppRoot.kt`: `FoodRouletteRoot` gets a new FIRST parameter `container: AppContainer` and wraps its
  content in `CompositionLocalProvider(LocalAppContainer provides container)`. `MainActivity` passes
  `(application as FoodRouletteApplication).container`.
  - `composable<HomeRoute>`: obtain `val favVm: FavoritesViewModel = viewModel(factory = container.viewModelFactory)`,
    `val favIds by favVm.ids.collectAsStateWithLifecycle()`, and pass to `RouletteScreen`:
    `favoriteIds = favIds, onToggleFavorite = { favVm.toggle(it) }, onOpenDetail = { navController.navigate(DetailRoute(it.id)) }`.
  - `composable<FavoritesRoute>`: `FavoritesPage(onOpenDetail = { navController.navigate(DetailRoute(it.id)) })`.
  - `composable<DetailRoute>`: `DetailPage(onBack = { navController.popBackStack() }, onOpenMapsUrl = onOpenMapsUrl)`.
  - The bottom bar stays hidden on `DetailRoute` (already true: it is not a top-level tab).

## 6. UI

### Shared: `<main>/ui/common/SubPageScaffold.kt`
`@Composable fun SubPageScaffold(title: String, onBack: () -> Unit, modifier: Modifier = Modifier, content: @Composable (PaddingValues) -> Unit)`
— Material3 `Scaffold(containerColor = colors.sheet)` with a `TopAppBar` (`@OptIn(ExperimentalMaterial3Api::class)`,
colors: container `colors.sheet`, title/icon `colors.ink`), title text 18.sp bold single line ellipsis,
navigation icon `IconButton(onClick = onBack) { Icon(painterResource(FoodIcon.Back.res), contentDescription = stringResource(R.string.back_desc)) }`.

### Icons
New `<res>/drawable/ic_heart_filled.xml`: same heart outline as `ic_heart.xml` but filled
(`android:fillColor="#FF000000"` on the heart path, keep the stroke). `FoodIcon.HeartFilled`.

### Home result actions (`<main>/ui/RouletteScreen.kt` and `<main>/ui/Panel.kt`)
- `RouletteScreen` new trailing params: `favoriteIds: Set<String> = emptySet()`, `onToggleFavorite: ((Shop) -> Unit)? = null`,
  `onOpenDetail: ((Shop) -> Unit)? = null`; pass them through to `Panel` (same names).
- `Panel` new trailing params with the same defaults. In the info row, when `phase == Result && result != null`:
  keep the existing centered pin + `parts.joinToString("・")` text exactly (tests look it up by that text), and
  when `onToggleFavorite != null` add after it a 36.dp `IconButton` with `FoodIcon.HeartFilled` (tint `colors.accent`)
  if `result.id in favoriteIds` else `FoodIcon.Heart` (tint `colors.muted`), contentDescription
  `R.string.favorite_remove_desc` / `R.string.favorite_add_desc`; when `onOpenDetail != null` add a `TextButton`
  labelled `R.string.btn_detail` (color `colors.accent`, 14.sp). When either callback is non-null, give the info-row
  `Box` `heightIn(min = 36.dp)` in every phase (instead of 22.dp) so the panel height does not jump; otherwise keep
  22.dp. With both callbacks null the panel must render exactly as before.

### Favorites tab: package `edu.android.wut2eat.ui.favorites`
- `FavoritesViewModel(favorites: FavoritesRepository, area: StateFlow<SearchArea>) : ViewModel`
  - `val items: StateFlow<List<Shop>?>` — `combine(favorites.favorites, area) { list, a -> list.map { it.copy(distKm = distanceKm(a.center, it.latLon)) } }`
    `.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)` (null = still loading)
  - `val ids: StateFlow<Set<String>>` — ids of the favorites (`stateIn(..., emptySet())`)
  - `fun remove(id: String)`, `fun toggle(shop: Shop)` (launch in `viewModelScope`)
- `FavoritesScreen(items: List<Shop>?, onOpen: (Shop) -> Unit, onRemove: (Shop) -> Unit, modifier: Modifier = Modifier, onDraw: (() -> Unit)? = null)`
  - Background `colors.sheet`, `statusBarsPadding()`; header row: title `R.string.tab_favorites` (22.sp bold) and,
    when `onDraw != null` and the list is non-empty, a small accent button `R.string.btn_draw_favorites` (wired in M3).
  - `items == null`: nothing but the header. Empty list: centered `FoodIcon.Heart` (40.dp, `colors.muted`) +
    `R.string.favorites_empty`.
  - Otherwise a `LazyColumn` (key = id) of cards (`Surface`, `RoundedCornerShape(12.dp)`, `colors.reel` background,
    1.dp `colors.ink.copy(alpha = 0.08f)` border, click → `onOpen`): name (16.sp bold, one line), info line
    `infoParts(shop).joinToString("・")` (13.sp `colors.muted`), and a trailing `IconButton` with `FoodIcon.HeartFilled`
    (tint `colors.accent`, contentDescription `stringResource(R.string.favorite_remove_named, shop.name)`) → `onRemove`.
- `FavoritesPage(onOpenDetail: (Shop) -> Unit, modifier: Modifier = Modifier)`.

### Detail page: package `edu.android.wut2eat.ui.detail`
- `sealed interface DetailUiState { data object Loading; data object NotFound; data class Loaded(val shop: Shop, val distKm: Double, val extras: ShopExtras, val isFavorite: Boolean) }`
- `DetailViewModel(shopId: String, lookup: ShopLookup, favorites: FavoritesRepository, area: StateFlow<SearchArea>) : ViewModel`
  - `val state: StateFlow<DetailUiState>`: look the shop up once (`flow { emit(lookup.find(shopId)) }`), then
    `flatMapLatest` to `flowOf(NotFound)` or `combine(favorites.favorites, area) { favs, a -> Loaded(shop, distanceKm(a.center, shop.latLon), fakeExtras(shop.id), favs.any { it.id == shop.id }) }`;
    `stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), DetailUiState.Loading)`.
  - `fun toggleFavorite()` — toggles the loaded shop (no-op otherwise).
- `DetailScreen(state: DetailUiState, onBack: () -> Unit, onToggleFavorite: () -> Unit, onOpenMaps: (Shop) -> Unit, modifier: Modifier = Modifier, onBook: ((Shop) -> Unit)? = null, onShare: ((Shop) -> Unit)? = null)`
  inside `SubPageScaffold(title = loaded shop name or R.string.detail_title, onBack)`, vertically scrollable column, 16.dp padding:
  - Loading: centered `R.string.info_booting`-style text `R.string.detail_loading`.
  - NotFound: `FoodIcon.Sad` + `R.string.detail_not_found` + an outlined button `R.string.btn_back` → `onBack`.
  - Loaded:
    1. Name (24.sp bold), line `type・formatDistance(distKm)` (14.sp muted).
    2. A small badge chip `R.string.demo_badge` (12.sp, `colors.accent2` border) before the fake section.
    3. Rating row: `R.string.detail_rating` with rating (one decimal) and reviews; price: `"$".repeat(priceLevel)` with label `R.string.detail_price`.
    4. Hours: `R.string.detail_hours` with `formatClock(open)`, `formatClock(close)`, then closed day:
       `R.string.detail_closed_day` with the weekday name from `R.array.weekday_names` (index closedWeekday-1), or `R.string.detail_open_every_day`.
    5. Section `R.string.detail_intro_label` + `stringArrayResource(R.array.fake_intros)` item `introIndex % size`.
    6. Section `R.string.detail_dishes_label` + 3 chips from `R.array.fake_dishes` (index `% size`).
    7. If `shop.note` is not blank: section `R.string.detail_note_label` + the note.
    8. Buttons (full width, 48.dp, 12.dp corners, same look as Panel's buttons): favorite toggle
       (`OutlinedButton`, `FoodIcon.HeartFilled`/`Heart`, text `R.string.btn_unfavorite` / `R.string.btn_favorite`) →
       `onToggleFavorite`; outlined `accent2` "在 Google Maps 開啟" (`R.string.btn_open_maps`, `FoodIcon.External`) →
       `onOpenMaps(shop)`; `onBook`/`onShare` buttons only when non-null (labels `R.string.btn_book`, `R.string.btn_share`).
- `DetailPage(onBack: () -> Unit, onOpenMapsUrl: (String) -> Unit, modifier: Modifier = Modifier)` → `onOpenMaps = { onOpenMapsUrl(mapsUrl(it)) }`.

### Strings (add to `<res>/values/strings.xml`)
`back_desc` 返回, `btn_back` 回上一頁, `btn_detail` 詳情, `favorite_add_desc` 加入收藏, `favorite_remove_desc` 取消收藏,
`favorite_remove_named` 從收藏移除 %1$s, `favorites_empty` 還沒有收藏，抽到喜歡的店按 ♡ 加入, `btn_draw_favorites` 從收藏抽,
`detail_title` 餐廳簡介, `detail_loading` 載入中…, `detail_not_found` 店家暫存資料已清除，請回上一頁重新抽,
`demo_badge` 示範資料, `detail_rating` ★ %1$.1f（%2$d 則評論）, `detail_price` 價位, `detail_hours` 營業時間 %1$s–%2$s,
`detail_closed_day` 每週%1$s公休, `detail_open_every_day` 全年無休, `detail_intro_label` 店家介紹,
`detail_dishes_label` 招牌菜, `detail_note_label` 備註, `btn_favorite` 加入收藏, `btn_unfavorite` 已收藏,
`btn_book` 預訂, `btn_share` 分享.
`string-array name="weekday_names"`: 一 二 三 四 五 六 日 (7 items).
`string-array name="fake_intros"`: exactly 8 short (40–70 字) fictional, warm restaurant introductions.
`string-array name="fake_dishes"`: exactly 16 dish names (e.g. 招牌豚骨拉麵, 古早味滷肉飯 …).

## 7. Tests

JVM (shared fake: `<test>/testing/FakeFavoritesRepository.kt`, package `edu.android.wut2eat.testing`, in-memory
`MutableStateFlow<List<Shop>>` implementing `FavoritesRepository` with the same semantics):
- `<test>/domain/FormatTest.kt`: ADD 1 test — custom and seed shops get the `query=lat,lon` URL (6 decimals), a
  Places id keeps `query_place_id`. Do not change existing tests.
- `<test>/domain/ShopExtrasTest.kt` (3): same id → equal extras; ranges hold for 200 ids (`"id$i"`); dish indices
  distinct and in range; plus `formatClock(690) == "11:30"` inside one of these.
- `<test>/domain/SeedShopsTest.kt` (1): 6 shops, unique `seed:` ids, operational, each within 1.5 km of `FALLBACK_POS`.
- `<test>/data/store/StoreCodecTest.kt` (3): round trip keeps every field except distKm (reset to 0.0); null/blank/corrupt
  input → empty list; unknown JSON fields are ignored.
- `<test>/data/DataStoreFavoritesRepositoryTest.kt` (3) on a REAL DataStore:
  `PreferenceDataStoreFactory.create(scope = CoroutineScope(Dispatchers.IO + SupervisorJob()), produceFile = { File(tmp.root, "test.preferences_pb") })`
  with a JUnit `@get:Rule val tmp = TemporaryFolder()`, cancel the scope in `@After`; use `runTest` and read with `.first()`.
  Cases: add/dedupe/newest-first + remove; toggle returns true then false; `seedIfFirstRun` twice → 6 seeds once, and
  after removing all seeds a third call does not re-add them.
- `<test>/data/ShopLookupTest.kt` (2): registry hit wins; falls back to favorites then `SEED_SHOPS`; unknown → null.
- `<test>/ui/favorites/FavoritesViewModelTest.kt` (2): items carry distance from `area.center`; toggle adds then removes.
  (Collect `stateIn` flows in `backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { ... collect {} }`.)
- `<test>/ui/detail/DetailViewModelTest.kt` (3): found → `Loaded` with `fakeExtras(id)` and distance; unknown → `NotFound`;
  `toggleFavorite()` flips `isFavorite`.
- `<test>/ui/RouletteHooksTest.kt` (2, package `edu.android.wut2eat.ui`, reuse `FakeRadiusStore`/`FakeLocationSource`/`FakeShopSearch`):
  startup location and `setRadius` are reported to `onAreaChanged`; `onDrawn` receives the drawn shop.

Instrumented:
- `<atest>/testing/TestDoubles.kt`: add
  `fun testContainer(context: Context, search: ShopSearch = { _, _ -> emptyList() }, location: LocationSource = FixedLocation(FALLBACK_POS)): AppContainer`
  using `PreferenceDataStoreFactory.create(produceFile = { File(context.cacheDir, "test-${UUID.randomUUID()}.preferences_pb") })`,
  `hasApiKey = true`, `isFatalError = { false }`.
- Update `<atest>/ui/nav/AppNavigationTest.kt` only as needed for the new `container` parameter (pass
  `testContainer(rule.activity, search)`); keep its two tests' intent.
- `<atest>/ui/favorites/FavoritesScreenTest.kt` (2): renders names + empty state; clicking a card calls `onOpen`, the
  remove button calls `onRemove`.
- `<atest>/ui/detail/DetailScreenTest.kt` (2): `Loaded` shows name, `demo_badge`, intro label, and the favorite button
  calls `onToggleFavorite`; `NotFound` shows `detail_not_found` and the back button calls `onBack`.
- `<atest>/ui/RouletteResultActionsTest.kt` (1, package `edu.android.wut2eat.ui`, use `MemoryRadiusStore`/`FixedLocation`
  from `testing`, NOT new fakes named `FakeRadiusStore`/`FakeLocationSource`): host `RouletteScreen` with
  `onToggleFavorite`/`onOpenDetail` callbacks, drive to Ready like `RouletteScreenTest`, spin a one-shop search, then the
  `favorite_add_desc` button and `btn_detail` are displayed and clicking `btn_detail` passes the shop to `onOpenDetail`.
  Close the scenario in `@After` like `RouletteScreenTest`.

Do not modify `RouletteViewModelTest.kt`, `RouletteScreenTest.kt`, or `RouletteViewModelVisibilityTest.kt`.
