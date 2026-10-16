# Milestone M6 spec: "write a restaurant location" page + share page

Read `gemini-rules.md` (same folder) first and follow it strictly. Read every existing file you modify in full
first, and the code you build on: `domain/ShopIds.kt`, `domain/Format.kt` (`mapsUrl`, `infoParts`), `domain/Extras.kt`,
`domain/FakeLocation.kt` (`PresetPlace`, `PRESET_PLACES`), `data/*.kt`, `data/store/StoreCodec.kt`, `data/ShopLookup.kt`,
`di/AppContainer.kt`, `ui/AppRoot.kt`, `MainActivity.kt`, `ui/common/LocationPicker.kt`, `ui/favorites/*`,
`ui/detail/*`, `ui/multi/*`, `ui/me/*`, `ui/RouletteScreen.kt`, `ui/Panel.kt`, and the fakes in `<test>/testing/`.
Shorthands `<main>/`, `<test>/`, `<atest>/`, `<res>/` as before. Same conventions. All text in `strings.xml`.
No new dependencies.

## 1. Domain — new `<main>/domain/NewShop.kt`
```kotlin
const val MAX_SHOP_NAME = 40
const val MAX_SHOP_NOTE = 100
/** 新增餐廳可選的類型（顯示用字串，與 Places 的 primaryTypeDisplayName 同性質） */
val SHOP_TYPES = listOf("餐廳", "小吃店", "咖啡廳", "拉麵店", "火鍋店", "早餐店", "甜品店", "速食店")
enum class NewShopError { NameRequired, NameTooLong, TypeRequired, NoteTooLong }
fun validateNewShop(name: String, type: String, note: String): Set<NewShopError>   // name/note checked after trim()
/** 自訂餐廳：id = CUSTOM_ID_PREFIX + uid，狀態視為營業中 */
fun newCustomShop(uid: String, name: String, type: String, note: String, pos: LatLon): Shop
```

## 2. Data
1. Move the DataStore preference keys into one place so a single `edit` can touch several of them: new
   `<main>/data/store/StoreKeys.kt` with `internal object StoreKeys { val FAVORITES = stringPreferencesKey("favorites_v1"); val SEEDED = booleanPreferencesKey("seeded_v1"); val CUSTOM_SHOPS = stringPreferencesKey("custom_shops_v1") }`
   (move the existing favorites/seeded keys there and reference them from `DataStoreFavoritesRepository`; key names unchanged).
   Other repositories may keep their own keys.
2. New `<main>/data/CustomShopRepository.kt`:
   ```kotlin
   interface CustomShopRepository {
       val shops: Flow<List<Shop>>                 // newest first
       /** 存成自訂餐廳並同時加入收藏（同一次 edit） */
       suspend fun createAndFavorite(shop: Shop)
   }
   class DataStoreCustomShopRepository(private val dataStore: DataStore<Preferences>) : CustomShopRepository
   ```
   `createAndFavorite`: ONE `dataStore.edit { }` that prepends the shop to `CUSTOM_SHOPS` and to `FAVORITES`
   (no duplicates by id), using `encodeShops`/`decodeShops`.
3. `ShopLookup`: add `customShops: CustomShopRepository`; order registry → favorites → custom shops → bookings → `SEED_SHOPS`.
   Update `AppContainer` and `<test>/data/ShopLookupTest.kt` construction (keep assertions; add one for custom shops).
4. `AppContainer`: `val customShops: CustomShopRepository = DataStoreCustomShopRepository(dataStore)`; constructor gets a
   trailing `newId: () -> String = { UUID.randomUUID().toString() }`; initializers:
   `AddShopViewModel(customShops = customShops, area = session.area, location = effectiveLocation, newId = newId)` and
   `ShareViewModel(shopId = createSavedStateHandle().toRoute<ShareRoute>().shopId, lookup = shopLookup, profile = profile)`.

## 3. Add-restaurant page — package `edu.android.wut2eat.ui.addshop`
```kotlin
data class AddShopUiState(
    val name: String = "",
    val type: String = "",
    val note: String = "",
    val pos: LatLon = FALLBACK_POS,
    val posLabel: String = "",            // preset name, or "" (UI shows coordinates)
    val errors: Set<NewShopError> = emptySet(),
    val locating: Boolean = false,
    val locateFailed: Boolean = false,
    val savedId: String? = null,          // set after a successful save → UI navigates to the detail page
)
class AddShopViewModel(
    private val customShops: CustomShopRepository,
    area: StateFlow<SearchArea>,
    private val location: LocationSource,
    private val newId: () -> String,
) : ViewModel() {
    val state: StateFlow<AddShopUiState>   // initial pos = area.value.center
    fun setName(v: String)   // take(MAX_SHOP_NAME + 10) so the error can still show; clears errors
    fun setType(v: String)
    fun setNote(v: String)
    fun pickPreset(p: PresetPlace)
    fun pickOnMap(pos: LatLon)
    fun useCurrent()          // location.current(); failure → locateFailed
    fun save()                // validate; errors → state.errors; else createAndFavorite(newCustomShop(newId(), name.trim(), type, note.trim(), pos)) → savedId
}
```
`AddShopScreen(state: AddShopUiState, onBack: () -> Unit, onNameChange: (String) -> Unit, onTypeChange: (String) -> Unit, onNoteChange: (String) -> Unit, onPickPreset: (PresetPlace) -> Unit, onPickMap: (LatLon) -> Unit, onUseCurrent: () -> Unit, onSave: () -> Unit, modifier: Modifier = Modifier)`
inside `SubPageScaffold(title = stringResource(R.string.add_shop_title), onBack)`, scrollable column, 16.dp padding, `imePadding()`:
1. `OutlinedTextField` name (label `R.string.add_shop_name`, single line, error state + supporting text for
   `NameRequired`/`NameTooLong`).
2. Section `R.string.add_shop_type`: `FlowRow` of `FilterChip`s from `SHOP_TYPES`; `R.string.add_shop_err_type` when `TypeRequired`.
3. `OutlinedTextField` note (label `R.string.add_shop_note`, up to 3 lines, supporting text `"${note.length}/$MAX_SHOP_NOTE"`,
   error for `NoteTooLong`).
4. Section `R.string.add_shop_location`: current value text (preset name or `R.string.fake_map_point` coordinates) and the
   shared `LocationPicker(selected = pos, onPickMap, onPickPreset, onUseCurrent = onUseCurrent)`; `R.string.fake_locate_failed`
   when `locateFailed`.
   Map-in-scroll conflict: add a parameter `onMapTouch: (Boolean) -> Unit = {}` to `LocationPicker` that reports when a
   finger is down on the map (wrap the map in a `Box` with
   `Modifier.pointerInput(Unit) { awaitEachGesture { awaitFirstDown(requireUnconsumed = false); onMapTouch(true); waitForUpOrCancellation(); onMapTouch(false) } }`
   — do not consume the events), and here disable the column's `verticalScroll(..., enabled = !mapTouched)` while touched.
5. Primary accent button `R.string.add_shop_save` → `onSave`.
`AddShopPage(onBack: () -> Unit, onSaved: (String) -> Unit, modifier: Modifier = Modifier)` — when `state.savedId` becomes
non-null call `onSaved(id)` once (`LaunchedEffect(state.savedId)`).
Navigation: `@Serializable data object AddShopRoute`; `composable<AddShopRoute>` with
`onSaved = { id -> navController.navigate(DetailRoute(id)) { popUpTo<AddShopRoute> { inclusive = true } } }`.
Entry points: `FavoritesScreen`/`FavoritesPage` get `onAddShop: (() -> Unit)? = null` → a header `TextButton` with
`FoodIcon.Plus` + `R.string.add_shop_short` (shown also when the list is empty); `MePage` gets
`onOpenAddShop = { navController.navigate(AddShopRoute) }` (the row already exists behind the nullable parameter).

## 4. Share page — package `edu.android.wut2eat.ui.share`
```kotlin
data class ShareUiState(val loading: Boolean = true, val notFound: Boolean = false, val shop: Shop? = null,
    val extras: ShopExtras? = null, val nickname: String = "", val note: String = "", val url: String = "")
class ShareViewModel(shopId: String, private val lookup: ShopLookup, private val profile: ProfileRepository) : ViewModel() {
    val state: StateFlow<ShareUiState>    // init: find shop; url = mapsUrl(shop); extras = fakeExtras(shop.id); nickname from profile
    fun setNote(v: String)                // take(MAX_SHARE_NOTE = 60)
}
```
(Put `const val MAX_SHARE_NOTE = 60` in the share package.)
`ShareScreen(state: ShareUiState, onBack: () -> Unit, onNoteChange: (String) -> Unit, onShare: (String) -> Unit, onCopyLink: (String) -> Unit, modifier: Modifier = Modifier)`
inside `SubPageScaffold(title = stringResource(R.string.share_title), onBack)`:
- Loading / not found like the detail page.
- Compose the share text in the screen:
  `val sender = nickname.ifBlank { stringResource(R.string.me_default_name) }`,
  `val noteText = note.ifBlank { stringResource(R.string.share_default_note) }`,
  `val text = stringResource(R.string.share_template, sender, shop.name, shop.type, noteText, url)` — the shop `type`
  only, no distance (it is meaningless for the receiver).
- A preview card (looks like a chat message bubble: `colors.reel` background, 16.dp corners, 1.dp border): sender line
  with a small `Avatar`-like circle is optional; shop name (18.sp bold), type, `★ rating` from `extras` with the
  `R.string.demo_badge` chip, the note text, and the url (single line, ellipsis, `colors.me`).
- `OutlinedTextField` note (label `R.string.share_note_label`, supporting `"${note.length}/$MAX_SHARE_NOTE"`).
- Primary accent button `R.string.share_send` with `FoodIcon.Share` → `onShare(text)`; `OutlinedButton`
  `R.string.share_copy` → `onCopyLink(url)`, after which show `R.string.share_copied` under it (local state).
`SharePage(onBack: () -> Unit, onShareText: (String) -> Unit, modifier: Modifier = Modifier)`; copying is done inside
`SharePage` with `LocalClipboard.current` + `rememberCoroutineScope()`:
`clipboard.setClipEntry(ClipEntry(ClipData.newPlainText("url", url)))`.

`MainActivity`: add
```kotlin
private fun shareText(text: String) {
    val send = Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text) }
    try { startActivity(Intent.createChooser(send, getString(R.string.share_chooser_title))) }
    catch (_: Exception) { Toast.makeText(this, R.string.share_no_app, Toast.LENGTH_SHORT).show() }
}
```
and pass `onShareText = ::shareText` to `FoodRouletteRoot` (new parameter `onShareText: (String) -> Unit = {}`).

Navigation: `@Serializable data class ShareRoute(val shopId: String)`; `composable<ShareRoute>`. Entry points
(`navController.navigate(ShareRoute(shop.id))`): `DetailPage` gets `onShare: (Shop) -> Unit` forwarded to
`DetailScreen.onShare`; the multiplayer winner card gets a `TextButton` `R.string.btn_share` (new `onShare: (Shop) -> Unit`
parameter on `MultiplayerScreen`/`MultiplayerPage`); Home: `RouletteScreen`/`Panel` get `onShare: ((Shop) -> Unit)? = null`
→ an `IconButton` with `FoodIcon.Share` (contentDescription `R.string.btn_share`) in the result info row next to the heart.
Update existing instrumented-test call sites only as needed to compile.

New hand-drawn icons (same style): `ic_share.xml` (three connected dots), `ic_plus.xml`; `FoodIcon.Share`, `FoodIcon.Plus`.

## 5. Strings
`add_shop_short` 新增, `add_shop_name` 餐廳名稱, `add_shop_type` 類型, `add_shop_note` 地址或備註（選填）,
`add_shop_location` 位置, `add_shop_save` 儲存並加入收藏, `add_shop_err_name` 請填寫餐廳名稱,
`add_shop_err_name_long` 名稱最多 40 字, `add_shop_err_type` 請選擇類型, `add_shop_err_note` 備註最多 100 字,
`share_title` 分享餐廳, `share_note_label` 想說的話, `share_default_note` 今天就吃這間！,
`share_template` %1$s 推薦你一間餐廳：\n%2$s（%3$s）\n%4$s\n%5$s, `share_send` 分享給朋友, `share_copy` 複製連結,
`share_copied` 已複製連結, `share_chooser_title` 分享餐廳, `share_no_app` 找不到可分享的應用程式.
(`add_shop_title` 新增餐廳 already exists from M4 — reuse it.)

## 6. Tests
JVM (add `FakeCustomShopRepository` to `<test>/testing/`; it should also add to a given `FakeFavoritesRepository` to mirror
`createAndFavorite`):
- `<test>/domain/NewShopValidationTest.kt` (2): each error case (blank/whitespace name, 41-char name, blank type,
  101-char note) and a valid input → empty set; `newCustomShop` builds a `custom:` id with operational status and the given position.
- `<test>/data/DataStoreCustomShopRepositoryTest.kt` (2): real DataStore; `createAndFavorite` makes the shop appear in BOTH
  `customShops.shops` and a `DataStoreFavoritesRepository` on the same DataStore; creating two keeps newest first.
- `<test>/ui/addshop/AddShopViewModelTest.kt` (3): initial pos = area center; `save()` with errors does not write;
  valid save writes a `custom:<newId>` shop and sets `savedId`; `pickPreset` updates pos/label.
- `<test>/ui/share/ShareViewModelTest.kt` (2): loads shop/url/extras/nickname; unknown id → `notFound`; `setNote` truncates to 60.
- `<test>/data/ShopLookupTest.kt`: ADD 1 test — a custom shop is found.

Instrumented:
- `<atest>/ui/addshop/AddShopScreenTest.kt` (1): typing a name calls `onNameChange`, clicking a type chip calls
  `onTypeChange`, clicking `add_shop_save` calls `onSave`; an error state shows `add_shop_err_name`.
- `<atest>/ui/share/ShareScreenTest.kt` (2): preview shows the shop name and the default note; `share_send` passes text that
  contains the shop name and url to `onShare`; `share_copy` passes the url to `onCopyLink` and then shows `share_copied`.

## 7. Conventions already in the codebase (follow them)
- Navigation in `ui/AppRoot.kt`: every sub-page navigation and back action is wrapped in `entry.ifResumed { … }` and
  sub-page `navigate(...)` calls pass `{ launchSingleTop = true }` (see the existing composables). For `AddShopRoute`'s
  `onSaved` use `navigate(DetailRoute(id)) { popUpTo<AddShopRoute> { inclusive = true }; launchSingleTop = true }`.
- `ShopLookup` currently takes `(registry, favorites, bookings)`; add `customShops` so the order becomes
  registry → favorites → custom shops → bookings → `SEED_SHOPS`.
- `AppContainer` constructor currently ends with `appScope` and `clock`; add `newId` after `clock`.
- Instrumented tests: the CI emulator screen is short (≈720x1280). Before `assertIsDisplayed()` / `performClick()` on
  any node of a vertically scrollable screen, call `.performScrollTo()` on it first. Compose rules: one `setContent`
  per test.
- Every file ends with exactly one newline; no stray double blank lines.

## 8. Lessons from earlier milestones (reviewers rejected these before — get them right the first time)
1. Compose tests: exactly ONE `setContent` per test; hoist state into the test if you need to change it.
2. When a text can appear twice on screen (e.g. a title and a heading), use `onAllNodesWithText(...)` and assert the count
   instead of `onNodeWithText(...)`.
3. A `Text` inside a `Row` next to buttons gets `Modifier.weight(1f, fill = false)`; rows containing Material buttons /
   clickable rows are at least 48.dp tall (`heightIn(min = 48.dp)`); every icon-only button has a `contentDescription`.
4. Rows of chips use `FlowRow` (or `LazyRow`), never a plain `Row` that can overflow.
5. No side effects (repository writes, callbacks, launching coroutines) inside `MutableStateFlow.update { }` lambdas —
   compute inside, act after.
6. Guard against double taps synchronously: e.g. `save()` must ignore a second call while the first is still writing
   (a `saving` flag set before launching), so a double tap cannot create two custom shops.
7. Do a one-time lookup per ViewModel once (cache the `Deferred`/result); do not re-run it on every resubscription of a
   `stateIn(WhileSubscribed)` flow.
8. Test data must be consistent with the rules under test (positions within the radius, valid names, etc.).
9. Every file ends with exactly one newline; no double blank lines anywhere.
10. A collection whose size must match a count constant needs a size test and defensive indexing.
11. Instrumented tests on scrollable screens: `.performScrollTo()` before `assertIsDisplayed()` / `performClick()`.

## 9. Small clean-ups in files you touch anyway
- `ui/multi/MultiplayerScreen.kt` and `ui/me/MeScreen.kt`: lint `ModifierParameter` — `modifier: Modifier = Modifier`
  must be the FIRST optional (defaulted) parameter of each public composable; move it there and keep every call site
  compiling (call sites use named arguments). Remove the stray double blank lines in both files.
