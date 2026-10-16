# Milestone M7 spec: end-to-end flows and hardening

Read `gemini-rules.md` (same folder) first and follow it strictly. Read every existing file you modify in full first.
Shorthands: `<main>/` = `app/src/main/java/edu/android/wut2eat/`, `<test>/` = `app/src/test/java/edu/android/wut2eat/`,
`<atest>/` = `app/src/androidTest/java/edu/android/wut2eat/`, `<res>/` = `app/src/main/res/`.
All user-visible text in `strings.xml`. No new dependencies.

## 1. Theme — FilterChip colours (`<main>/ui/theme/Theme.kt`)
Selected `FilterChip`s use Material's default lavender because the colour schemes do not set the secondary container.
In both `lightColorScheme(...)` and `darkColorScheme(...)` of `FoodRouletteTheme` also pass
`secondaryContainer` and `onSecondaryContainer`:
- light: `secondaryContainer = Color(0xFFFCE3D9)` (a light tint of the accent), `onSecondaryContainer = c.ink`;
- dark: `secondaryContainer = Color(0xFF4B2A45)`, `onSecondaryContainer = c.ink`.
Keep everything else in the function unchanged.

## 2. Places language (`<main>/data/PlacesSearch.kt`)
Results show English type names ("Breakfast Restaurant") on an English device while the UI is Traditional Chinese.
Initialise Places with the app's language: `Places.initializeWithNewPlacesApiEnabled(context.applicationContext, apiKey, Locale.TAIWAN)`
(`java.util.Locale`). Add a one-line Chinese comment explaining why.

## 3. Maps renderer (`<main>/FoodRouletteApplication.kt`)
Right after an emulator/device reboot Play services sometimes picks the LEGACY Maps renderer, which never reported the map
as loaded (Home then hit its 15 s map-load timeout). Request the latest renderer once at start-up:
```kotlin
override fun onCreate() {
    super.onCreate()
    // 要求新版地圖渲染器；剛開機時 Play 服務可能退回舊版，地圖不會回報載入完成
    MapsInitializer.initialize(this, MapsInitializer.Renderer.LATEST) { }
}
```
(`com.google.android.gms.maps.MapsInitializer`). Keep the lazy `container` exactly as it is.

## 4. 自訂定位 page (`<main>/ui/location/FakeLocationScreen.kt`)
1. "Never picked" state: when the setting is the untouched default — `!setting.enabled && setting.label.isBlank() &&
   setting.pos == FALLBACK_POS` — and also while `setting == null`, show `stringResource(R.string.fake_current, stringResource(R.string.fake_not_set))`
   instead of the fallback coordinates. New string `fake_not_set` = `未設定`.
2. The `LocationPicker` sits inside a `verticalScroll` column, so vertical drags scroll the page instead of panning the map.
   Do what `ui/addshop/AddShopScreen.kt` does: `var mapTouched by remember { mutableStateOf(false) }`,
   `.verticalScroll(rememberScrollState(), enabled = !mapTouched)`, and `LocationPicker(..., onMapTouch = { mapTouched = it })`.

## 5. 我的 avatar colours — touch targets (`<main>/ui/me/MeScreen.kt`)
The six colour circles are 32.dp clickable boxes (below the 48.dp minimum). Make each item a 48.dp touch target that keeps the
32.dp visual circle: an outer `Box(Modifier.size(48.dp).selectable(selected = isSelected, role = Role.RadioButton, onClick = { onSetAvatar(i) }).semantics { contentDescription = desc }, contentAlignment = Alignment.Center)`
containing the existing 32.dp circle (border when selected, clip, background) without its own `clickable`/semantics.
Reduce the `Row`'s `spacedBy` from 8.dp to 0.dp so the row width stays about the same (6 × 48 = 288.dp fits a 360dp phone
inside the card). Keep `me_avatar_desc`. Existing `MeScreenTest` must keep passing (it may click an avatar by its description).

## 6. Booking form errors (`<main>/ui/booking/BookingViewModel.kt`, `<main>/ui/booking/BookingScreen.kt`)
1. `selectDate`, `selectTime`, `setParty`, `setName`, and `setNote` also set `error = null` (inside the same `copy`), so a
   message such as 請填寫訂位人 disappears as soon as the user edits the form (it is shown again on the next `submit` if still invalid).
2. In `BookingScreen` the validation error message (the block under `if (state.error != null)`) uses
   `MaterialTheme.colorScheme.error` for its text (and border, if it has one) instead of `colors.accent2`, matching the
   red error colour of the text fields. Do not change other `accent2` uses (badges, notices).
3. `<main>/ui/addshop/AddShopScreen.kt`: the 請選擇類型 error text also uses `MaterialTheme.colorScheme.error`
   (the 目前位置 failure notice stays `accent2`).
4. JVM test (add to `<test>/ui/booking/BookingViewModelTest.kt`, 1 new test): with the fixed clock and a blank name,
   `submit()` → `state.error == BookingError.NameRequired`; then `setName("小明")` → `state.error == null` and still
   nothing saved; then `submit()` → confirmed and saved.

## 7. Share page polish
1. `<main>/ui/share/ShareViewModel.kt`: `ShareUiState` gains `val avatar: Int = 0`, loaded from the profile together with the nickname.
   Update `<test>/ui/share/ShareViewModelTest.kt` to assert the avatar index too (no new test).
2. `<main>/ui/share/ShareScreen.kt`: replace the hand-made 24.dp accent circle with the shared
   `ui/common/Avatar(nickname = state.nickname, colorIndex = state.avatar, size = 24.dp)` so the initial and colour match
   the 我的 tab (a blank nickname shows 食). The sender line text stays `sender` (nickname or 美食探險家).
3. `<main>/MainActivity.kt` `shareText`: also `putExtra(Intent.EXTRA_TITLE, getString(R.string.share_chooser_title))` on the
   send intent (Android 14+ shows it in the share sheet; the chooser title alone is ignored for text).

## 8. End-to-end UI test — new `<atest>/ui/AppFlowTest.kt` (package `edu.android.wut2eat.ui`, 3 tests)
Model it on `<atest>/ui/nav/AppNavigationTest.kt` (rule, `testScope`, `here = LatLon(24.1369, 120.685)`, tearDown that
cancels the scope, calls `clearTestDataStores(rule.activity)` and closes the scenario). Differences:
- Obtain Home's ViewModel FROM THE CONTAINER so the real hooks are wired (drawn shops are registered for `ShopLookup`):
  inside `rule.runOnUiThread { container = testContainer(rule.activity, search, FixedLocation(here), testScope); vm = ViewModelProvider(rule.activity, container.viewModelFactory)[RouletteViewModel::class.java] }`.
- `FoodRouletteRoot(container = container, rouletteViewModel = vm, onOpenMapsUrl = {}, onShareText = { sharedText = it })`.
- After `setContent`: `waitForIdle()`, then on the UI thread `vm.startup(); vm.onMapLoaded()`, then wait until `Phase.Ready`.
- Navigation callbacks are guarded by `entry.ifResumed { … }`: a click during a page transition is ignored. After every
  click that navigates, call `rule.waitForIdle()` and then `rule.waitUntil(TIMEOUT_MS) { …a node unique to the target page exists… }`
  before interacting with the new page. Use `TIMEOUT_MS = 15_000L`.
- Every node on a scrollable page: `.performScrollTo()` before `assertIsDisplayed()` / `performClick()` / `performTextInput()`.
- Exactly one `setContent` per test. The bottom bar is hidden on sub-pages: go back with the top bar's back button
  (`onNodeWithContentDescription(string(R.string.back_desc))`) before tapping a tab.
- To read data the UI cannot show deterministically, use the container in the test, e.g.
  `runBlocking { container.bookings.bookings.first() }`.

Tests:
1. `favoritesDraw_opensDetail_andBookingAppearsOnMe` — tap the 收藏 tab; wait until the seed shop 綠川拉麵屋 is shown
   (seeding runs in the container's scope); tap `btn_draw_favorites`; on the draw page tap `btn_draw_one`; wait until
   `btn_detail` exists (result); tap it; on the detail page wait for `demo_badge`, tap `btn_book`; on the booking page
   type a name into the `booking_name` field and tap `btn_confirm_booking`; wait for `btn_done`; read the saved booking code
   from `container.bookings` and assert the code is displayed; tap `btn_done` (back to detail); press back twice (detail →
   draw page → 收藏 tab); tap the 我的 tab; assert `me_bookings_empty` does not exist and the booking code text is displayed
   (`onNodeWithText(code, substring = true)`).
2. `addShop_appearsInFavoritesAndDrawPool` — tap the 收藏 tab; wait for 綠川拉麵屋; tap `add_shop_short`; type
   `Test Noodle` into the `add_shop_name` field; tap the `拉麵店` chip; tap the first preset chip (`PRESET_PLACES[0].name`);
   tap `add_shop_save`; wait until the detail page shows `Test Noodle` and `demo_badge`; press back → the 收藏 tab shows
   `Test Noodle` (it is first, so it is visible); `runBlocking { container.customShops.shops.first() }` has exactly that
   one shop with a `custom:` id; tap `btn_draw_favorites` → the draw page shows `fav_draw_count` with 7 (6 seeds + 1).
3. `homeResult_shareSendsText` — search returns one Places shop near `here` (like AppNavigationTest's `shop`); tap
   `btn_spin`; wait for `Phase.Result`; tap the node with content description `btn_share`; wait until the share page shows
   the shop name; tap `share_send`; assert `sharedText` contains the shop name and `mapsUrl(shop)`.

## 9. Small Compose test addition (`<atest>/ui/location/FakeLocationScreenTest.kt`, 1 new test)
With `FakeLocationUiState(setting = FakeLocation())` (the untouched default; read the real state class first and build
it accordingly), the page shows `fake_current` with `fake_not_set` (`string(R.string.fake_current, string(R.string.fake_not_set))`).

## 10. Lessons from earlier milestones (reviewers rejected these before — get them right the first time)
1. Compose tests: exactly ONE `setContent` per test.
2. Duplicate texts on one screen → `onAllNodesWithText(...)` and assert the count / `[0]`.
3. A `Text` in a `Row` next to buttons gets `Modifier.weight(1f, fill = false)`; clickable rows ≥ 48.dp; icon-only buttons have a `contentDescription`.
4. Chip rows use `FlowRow`/`LazyRow`.
5. No side effects inside `MutableStateFlow.update { }`.
6. Synchronous double-tap guards.
7. One-time lookups are cached per ViewModel.
8. Test data consistent with the rules under test (positions within the radius, valid names, ...).
9. Every file ends with exactly one newline; no double blank lines anywhere.
10. Collections whose size must match a constant need a size test and defensive indexing.
11. `.performScrollTo()` before `assertIsDisplayed()` / `performClick()` on scrollable screens (the CI emulator screen is ≈720x1280).

Expected totals after this milestone: JVM 116 tests (115 + 1); instrumented 26 tests in 13 classes (22 + 3 AppFlowTest + 1 FakeLocationScreenTest).
