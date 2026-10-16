# Items collected for M7 (hardening)

- FilterChip selected colour is Material's default lavender (theme lacks secondaryContainer) — set
  `secondaryContainer`/`onSecondaryContainer` in `FoodRouletteTheme`'s colour schemes (e.g. accent at low alpha / ink)
  so every FilterChip (multiplayer pool, location presets, booking chips) matches the app palette.
- 自訂定位 page: when no fake location was ever saved (default `FakeLocation()` label "" at FALLBACK_POS, disabled), it
  shows 地圖選點（24.1369, 120.6850）; show 未設定 when disabled and never picked.
- Me tab avatar colour circles are 32dp (< 48dp touch target) — enlarge the touch area.
- Fake dishes ignore shop type (ramen shop lists 起司塔) — optional: pick dishes by type keyword.
- Home result shows English Places type ("Breakfast Restaurant") when the device locale is English — optional:
  `setLanguageCode` / rely on device locale; document.
- AppFlowTest end-to-end flows, accessibility pass, R8 check (`:app:analyzeReleaseR8Config`), README 10-screen list.
- Booking: `setName`/`setNote`/date/time changes should clear `error` (請填寫訂位人 stays until next submit).
- (from M6 smoke) Add-shop page: 請選擇類型 uses `colors.accent2` (orange) while the text-field errors are red — use one
  error colour (`MaterialTheme.colorScheme.error`) for all form errors (add shop, booking, fake location).
- (M6) Share card avatar shows the first char of 美食探險家 (美) while 我的 shows 食 — reuse `ui/common/Avatar` with the
  profile's avatar colour (ShareUiState needs the avatar index).
- (M6) Android 14+ chooser ignores the `createChooser` title for text — also put `Intent.EXTRA_TITLE` on the send intent.
- (M6) LocationPicker: after a configuration change (display size) the 10 s "map not loaded" hint appeared over a loaded
  map for a few seconds — check `mapLoaded`/timer state is `rememberSaveable`/keyed correctly.
- (M6) Home map never reported loaded right after an emulator reboot: Play services picked the LEGACY renderer
  (`preferredRenderer: null`); later launches got LATEST and loaded fine. Consider
  `MapsInitializer.initialize(context, Renderer.LATEST) {}` in `FoodRouletteApplication` and document it.
- (M6 docs review) `ui/location/FakeLocationScreen.kt` puts `LocationPicker` in a `verticalScroll` column without
  `onMapTouch` — on a short screen vertical drags scroll the page instead of panning; wire it like `AddShopScreen`.
