# M2 review round 3 — PR #3 merge-gate review requested changes (same rules: no git, no shell, only these files)

An independent reviewer found two must-fix bugs and two test gaps. Apply exactly these changes:

1. `app/src/main/java/edu/android/wut2eat/ui/detail/DetailViewModel.kt` — the shop lookup must run ONCE per ViewModel.
   Today `flow { emit(lookup.find(shopId)) }` sits upstream of `stateIn(WhileSubscribed(5_000))`, so it re-runs every
   time collection restarts (e.g. the user leaves for Google Maps > 5 s and comes back). If the user un-favorited a
   Places shop that is not in the in-memory registry, the second lookup misses and the page turns into NotFound.
   Fix: resolve once and cache, e.g.
   ```kotlin
   private val shop: Deferred<Shop?> = viewModelScope.async { lookup.find(shopId) }
   ```
   and use `flow { emit(shop.await()) }` as the upstream (keep the rest of the pipeline and `toggleFavorite()` behaviour).
   Add a test to `app/src/test/java/edu/android/wut2eat/ui/detail/DetailViewModelTest.kt`: a shop found only in
   favorites → `Loaded`; toggle it off (no longer a favorite); cancel the collector; `advanceTimeBy(5_001)`; start a new
   collector → state is still `Loaded` with `isFavorite == false` (and the lookup ran once — count calls with a small
   counting wrapper/fake if convenient).
2. `app/src/main/java/edu/android/wut2eat/ui/Panel.kt` — the info-row `Box` reserves `heightIn(min = 36.dp)` when
   actions are present, but Material3 `TextButton`/`IconButton` enforce a 48.dp minimum interactive size, so the row
   becomes 48.dp only in the Result phase and the panel still jumps. Change the reserved height to
   `heightIn(min = if (hasActions) 48.dp else 22.dp)` (keep everything else).
3. `app/src/test/java/edu/android/wut2eat/data/ShopLookupTest.kt` — assert the documented priority where two sources
   hold the SAME id: (a) the same id with different names in the registry and in favorites → the registry copy wins;
   (b) a favorite with id `seed:02` and a different name → the favorites copy beats `SEED_SHOPS`. Add these as one new
   test (so the class goes from 2 to 3 tests).
4. `app/src/androidTest/java/edu/android/wut2eat/ui/RouletteResultActionsTest.kt` — `toggledShop` is assigned but never
   asserted. After checking the buttons are displayed, click the `favorite_add_desc` node and
   `assertEquals(shop.id, toggledShop?.id)`, then keep the existing 詳情 click + assertion.

Reply with the list of files you changed.
