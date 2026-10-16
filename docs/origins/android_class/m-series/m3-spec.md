# Milestone M3 spec: favorites draw page + four-player draw page

Read `gemini-rules.md` (same folder) first and follow it strictly. Read every existing file you modify in full
first, and read the code you build on: `ui/RouletteViewModel.kt` (`ReelSpin`, `REEL_TIMEOUT_MS`), `ui/Reel.kt`,
`ui/Panel.kt`, `ui/AppRoot.kt`, `di/AppContainer.kt`, `di/LocalAppContainer.kt`, `data/Session.kt`,
`data/FavoritesRepository.kt`, `ui/favorites/*`, `ui/detail/*`, `ui/common/SubPageScaffold.kt`, `domain/Pick.kt`,
`domain/Sample.kt`, and the test helpers `<test>/testing/FakeFavoritesRepository.kt` and
`<test>/ui/RouletteViewModelTest.kt` (its public `FakeShopSearch`). Path shorthands as before:
`<main>/` = `app/src/main/java/edu/android/wut2eat/`, `<test>/`, `<atest>/`, `<res>/`.
Same conventions as M2: `XxxViewModel` (plain constructor args), stateless `XxxScreen`, stateful `XxxPage`
using `viewModel(factory = LocalAppContainer.current.viewModelFactory)`. All text in `strings.xml`. No new dependencies.

## 1. Domain (pure Kotlin)

New `<main>/domain/Pool.kt`:
```kotlin
/** 從固定清單抽（收藏、多人抽的池）：距離以 here 計算；不篩營業狀態與半徑。空清單回傳 null。 */
fun drawFromPool(pool: List<Shop>, here: LatLon, rand: () -> Double = Math::random): Draw?
/** 0 until n 的隨機索引；n 必須 > 0 */
fun pickIndex(n: Int, rand: () -> Double = Math::random): Int
```
`drawFromPool`: map every shop to `copy(distKm = distanceKm(here, it.latLon))`, then `pickRandom` → `Draw(chosen, pool)`.
`pickIndex`: `(rand() * n).toInt().coerceIn(0, n - 1)`.

## 2. Shared UI helpers

1. New `<main>/ui/common/ReelGate.kt` — lets a ViewModel wait for any number of concurrent reel animations:
   ```kotlin
   /** 等待滾輪動畫結束：每次轉動 begin() 拿 id，UI 動畫結束呼叫 finish(id)；最多等 timeoutMs（UI 不在畫面上時不會回報）。 */
   class ReelGate {
       fun begin(): Int
       fun finish(id: Int)
       suspend fun await(id: Int, timeoutMs: Long = REEL_TIMEOUT_MS)
   }
   ```
   Backed by a `mutableMapOf<Int, CompletableDeferred<Unit>>` and an incrementing id (start at 1); `await` uses
   `withTimeoutOrNull` and removes the entry afterwards; `finish` of an unknown id is a no-op. Used only from the main thread.
2. New `<main>/ui/common/ReducedMotion.kt`: move the reduced-motion detection that is inline in `Panel.kt`
   (reads `Settings.Global.ANIMATOR_DURATION_SCALE`) into `@Composable fun rememberReducedMotion(): Boolean`, and make
   `Panel` call it. Behaviour must be identical.

## 3. Data

1. New `<main>/data/NearbyPoolCache.kt`:
   ```kotlin
   /** 多人抽「附近」池：同一區域（中心四捨五入到 1e-3 度＋半徑）只查一次；並發呼叫共用同一次查詢。 */
   class NearbyPoolCache {
       suspend fun get(area: SearchArea, fetch: suspend (SearchArea) -> List<Shop>): List<Shop>
       fun clear()
   }
   ```
   Guard with a `kotlinx.coroutines.sync.Mutex` (`withLock`) so concurrent callers wait for the first fetch. Cache only
   non-empty results; exceptions propagate and are not cached. Key: `"%.3f,%.3f,%.1f"` (Locale.US) of lat, lon, radius.
2. `Session` (`<main>/data/Session.kt`): add `val nearby = NearbyPoolCache()`.
3. New `<main>/data/StatsRepository.kt`:
   ```kotlin
   /** 累計抽籤次數（每次滾輪抽出一間店算一次；多人抽每位玩家各算一次，決勝不算） */
   interface StatsRepository { val drawCount: Flow<Int>; suspend fun addDraw() }
   class DataStoreStatsRepository(private val dataStore: DataStore<Preferences>) : StatsRepository
   ```
   Key `intPreferencesKey("draw_count")`; same IOException `catch` pattern as `DataStoreFavoritesRepository`.
4. `AppContainer`:
   - `val stats: StatsRepository = DataStoreStatsRepository(dataStore)`.
   - A private `recordDraw: (Shop) -> Unit = { shop -> session.registry.put(shop); appScope.launch { stats.addDraw() } }`,
     used as the Roulette hooks' `onDrawn` (replacing the registry-only lambda) and passed to the new ViewModels.
   - Initializers for `FavoritesDrawViewModel(favorites = favorites, area = session.area, onDrawn = recordDraw)` and
     `MultiplayerViewModel(area = session.area, search = search, favorites = favorites, cache = session.nearby, hasApiKey = hasApiKey, isFatalError = isFatalError, onDrawn = recordDraw)`.

## 4. Favorites draw page — package `edu.android.wut2eat.ui.favdraw`

```kotlin
enum class FavDrawPhase { Idle, Spinning, Result, Empty }
data class FavDrawUiState(
    val phase: FavDrawPhase = FavDrawPhase.Idle,
    val count: Int = 0,          // 收藏數
    val reel: ReelSpin? = null,
    val result: Shop? = null,
)
class FavoritesDrawViewModel(
    private val favorites: FavoritesRepository,
    private val area: StateFlow<SearchArea>,
    private val rand: () -> Double = Math::random,
    private val onDrawn: (Shop) -> Unit = {},
) : ViewModel() {
    val state: StateFlow<FavDrawUiState>
    fun draw()
    fun onReelFinished(id: Int)
}
```
- `init`: collect `favorites.favorites`; update `count`; when not spinning: count 0 → phase `Empty`; count > 0 and phase
  `Empty` → `Idle`.
- `draw()`: ignore while `Spinning`; `val list = favorites.favorites.first()`; `drawFromPool(list, area.value.center, rand)`
  null → `Empty`; else `id = gate.begin()`, state = `Spinning` with `reel = ReelSpin(reelSequence(d.pool, d.chosen, rand), REEL_LEN - 1, id)`
  and `result = null`; then `gate.await(id)` → `Result` with `result = d.chosen`, and call `onDrawn(d.chosen)`.
- `onReelFinished(id)` → `gate.finish(id)`.

`FavoritesDrawScreen(state: FavDrawUiState, onDraw: () -> Unit, onReelFinished: (Int) -> Unit, onBack: () -> Unit, onOpenDetail: (Shop) -> Unit, modifier: Modifier = Modifier)`
inside `SubPageScaffold(title = stringResource(R.string.fav_draw_title), onBack)`:
- A card (`colors.sheet`/`colors.reel` like Panel, 16.dp corners) containing the existing `Reel` composable, using the
  same mapping as Panel's `ReelParams`: Spinning → animate the reel (`animationKey = reel.id`,
  `onFinished = { onReelFinished(reel.id) }`, `contentDesc = R.string.reel_desc`); Result → static reel at
  `chosenIndex` with `contentDesc = stringResource(R.string.reel_result_desc, result.name)`; Idle → `R.string.reel_unknown`;
  Empty → `FoodIcon.Sad` icon reel like Panel's Empty case. `reducedMotion = rememberReducedMotion()`.
- Text `stringResource(R.string.fav_draw_count, count)` (13.sp muted) or `R.string.fav_draw_empty` when Empty.
- Primary accent button (same look as Panel's, 48.dp): label `R.string.btn_draw_one` (Idle/Empty) or
  `R.string.btn_spin_again` (Result), `FoodIcon.Dice`; disabled while Spinning or Empty.
- Result: a card with the shop name (18.sp bold), `infoParts(shop).joinToString("・")`, and a `TextButton`
  `R.string.btn_detail` → `onOpenDetail(shop)`.
`FavoritesDrawPage(onBack: () -> Unit, onOpenDetail: (Shop) -> Unit, modifier: Modifier = Modifier)`.

Navigation: add `@Serializable data object FavoritesDrawRoute` to `ui/nav/Routes.kt`; `composable<FavoritesDrawRoute>`
in `AppRoot.kt` (`onBack = { navController.popBackStack() }`, `onOpenDetail = { navController.navigate(DetailRoute(it.id)) }`);
in `composable<FavoritesRoute>` pass `onDraw = { navController.navigate(FavoritesDrawRoute) }` to `FavoritesPage`
(add that parameter to `FavoritesPage` and forward it to `FavoritesScreen.onDraw`).

## 5. Multiplayer page — package `edu.android.wut2eat.ui.multi`

```kotlin
const val PLAYER_COUNT = 4
enum class PoolSource { Nearby, Favorites }
data class PlayerSlot(val reel: ReelSpin? = null, val result: Shop? = null, val spinning: Boolean = false)
enum class MultiMessage { Empty, Error, NoApiKey }
data class MultiUiState(
    val source: PoolSource = PoolSource.Nearby,
    val slots: List<PlayerSlot> = List(PLAYER_COUNT) { PlayerSlot() },
    val message: MultiMessage? = null,
    val finalReel: ReelSpin? = null,
    val finalSpinning: Boolean = false,
    val winnerIndex: Int? = null,
) {
    /** 有玩家在等抽籤池（還沒有滾輪） */
    val loadingPool: Boolean get() = slots.any { it.spinning && it.reel == null }
    val canDecide: Boolean get() = !finalSpinning && slots.all { it.result != null && !it.spinning }
    val winner: Shop? get() = winnerIndex?.let { slots[it].result }
}
class MultiplayerViewModel(
    private val area: StateFlow<SearchArea>,
    private val search: ShopSearch,
    private val favorites: FavoritesRepository,
    private val cache: NearbyPoolCache,
    private val hasApiKey: Boolean = true,
    private val isFatalError: (Throwable) -> Boolean = { false },
    private val rand: () -> Double = Math::random,
    private val onDrawn: (Shop) -> Unit = {},
) : ViewModel() {
    val state: StateFlow<MultiUiState>
    fun setSource(source: PoolSource)   // ignored while anything spins; otherwise resets slots/final/message
    fun draw(slot: Int)                 // each player's own button; slots run concurrently
    fun decide()                        // final pick among the 4 results; ignored unless canDecide
    fun onReelFinished(id: Int)         // for both slot reels and the final reel
    fun reset()                         // ignored while anything spins
}
```
- `draw(slot)`: ignore if that slot is spinning or `finalSpinning`. Set that slot `spinning = true` (keep nothing of its
  old reel/result), clear `winnerIndex`/`finalReel`, `message = null`. In `viewModelScope.launch`:
  1. `val pool = loadPool() ?: run { set slot spinning = false; return@launch }`.
  2. `val d = drawFromPool(pool, area.value.center, rand)` (non-null because the pool is non-empty).
  3. `id = gate.begin()`; slot `reel = ReelSpin(reelSequence(d.pool, d.chosen, rand), REEL_LEN - 1, id)`.
  4. `gate.await(id)`; slot `result = d.chosen, spinning = false`; `onDrawn(d.chosen)`.
- `private suspend fun loadPool(): List<Shop>?`:
  - Favorites: `favorites.favorites.first()`; empty → `message = Empty`, return null.
  - Nearby: if `!hasApiKey` → `message = NoApiKey`, null. Else
    `cache.get(area.value) { a -> drawShop(search, a.center, a.radiusKm, rand)?.pool.orEmpty() }` inside try/catch
    (rethrow `CancellationException`; any other exception → `message = Error`, null). Empty → `message = Empty`, null.
- `decide()`: `results = slots.map { it.result!! }`; `idx = pickIndex(PLAYER_COUNT, rand)`; `id = gate.begin()`;
  `finalReel = ReelSpin(reelSequence(results, results[idx], rand), REEL_LEN - 1, id)`, `finalSpinning = true`,
  `winnerIndex = null`; launch `gate.await(id)` → `winnerIndex = idx`, `finalSpinning = false`. (Not counted as a draw.)
- Use `_state.update { }` for every change (several slots finish concurrently; never read-modify-write a stale copy).

`MultiplayerScreen(state: MultiUiState, onSetSource: (PoolSource) -> Unit, onDraw: (Int) -> Unit, onReelFinished: (Int) -> Unit, onDecide: () -> Unit, onReset: () -> Unit, onOpenDetail: (Shop) -> Unit, modifier: Modifier = Modifier)`
— a top-level tab page (no back button), background `colors.sheet`, `statusBarsPadding()`, vertically scrollable, 16.dp padding:
1. Header: title `R.string.multi_title` (22.sp bold) + hint `R.string.multi_hint` (13.sp muted).
2. Source selector: two `FilterChip`s `R.string.multi_source_nearby` / `R.string.multi_source_favorites`
   (selected = current source; disabled while anything spins).
3. 2×2 grid (two `Row`s of two `PlayerCard`s with `Modifier.weight(1f)`, 12.dp gaps). `PlayerCard` (private): card with
   1.5.dp border in a per-player colour (use `colors.accent`, `colors.accent2`, `colors.me`, `colors.ink.copy(alpha = 0.6f)`),
   label `stringResource(R.string.multi_player, i + 1)`, a `Reel` (spinning → animate with `onFinished = { onReelFinished(reel.id) }`;
   result → static at `chosenIndex` with contentDesc `stringResource(R.string.multi_player_result_desc, i + 1, result.name)`;
   otherwise `R.string.reel_unknown`), and its own accent button with text
   `stringResource(R.string.multi_draw_player, i + 1)` → `onDraw(i)`, disabled while that slot spins or `finalSpinning`.
   Each button is independent so several can be pressed at the same time.
4. Status line: `R.string.multi_loading` while `loadingPool`; otherwise the message text for `Empty`/`Error`/`NoApiKey`
   (`R.string.multi_msg_empty` / `multi_msg_error` / `multi_msg_no_key`, colour `colors.accent2`).
5. Final section: a big `Reel` for `finalReel` (contentDesc `R.string.reel_desc` while spinning; when a winner exists,
   `stringResource(R.string.reel_result_desc, winner.name)`), the primary button `R.string.multi_decide` (enabled only when
   `canDecide`), and when `winner != null` a winner card: `stringResource(R.string.multi_winner, winner.name)` (18.sp bold),
   info line, `TextButton` `R.string.btn_detail` → `onOpenDetail(winner)`. An `OutlinedButton` `R.string.multi_reset` → `onReset`
   (disabled while anything spins).
`MultiplayerPage(onOpenDetail: (Shop) -> Unit, modifier: Modifier = Modifier)`; in `AppRoot.kt` replace the
`MultiplayerRoute` placeholder with `MultiplayerPage(onOpenDetail = { navController.navigate(DetailRoute(it.id)) })`.

## 6. Strings
`fav_draw_title` 從收藏抽, `fav_draw_count` 從 %1$d 間收藏中抽, `fav_draw_empty` 收藏是空的，先去抽幾間喜歡的店吧,
`btn_draw_one` 抽一間, `multi_title` 多人抽, `multi_hint` 四個人各按自己的按鈕，四家都出來後按「決勝」,
`multi_source_nearby` 附近, `multi_source_favorites` 收藏, `multi_player` 玩家 %1$d, `multi_draw_player` 玩家 %1$d 抽,
`multi_player_result_desc` 玩家 %1$d 抽到：%2$s, `multi_decide` 決勝, `multi_reset` 重來, `multi_winner` 就決定是：%1$s,
`multi_loading` 找附近的店中…, `multi_msg_empty` 抽籤池沒有店：附近找不到營業中的店，或收藏是空的,
`multi_msg_error` 地點服務暫時無法使用，請稍後再試, `multi_msg_no_key` 沒有地圖金鑰，請改用「收藏」抽籤池.

## 7. Tests

JVM (`StandardTestDispatcher` + `Dispatchers.setMain`; finish reels by `advanceTimeBy(REEL_TIMEOUT_MS + 1)` or `onReelFinished`;
reuse `edu.android.wut2eat.testing.FakeFavoritesRepository` and `edu.android.wut2eat.ui.FakeShopSearch`):
- `<test>/domain/PoolDrawTest.kt` (3): empty → null; chosen comes from the pool with `distKm` from `here`
  (deterministic `rand`); `pickIndex` stays in `0 until n` for rand values 0.0 and 0.999999.
- `<test>/ui/common/ReelGateTest.kt` (2): `finish` releases `await` immediately (virtual time unchanged); without
  `finish`, `await` returns after `REEL_TIMEOUT_MS`.
- `<test>/data/DataStoreStatsRepositoryTest.kt` (1): real DataStore as in `DataStoreFavoritesRepositoryTest`; starts at 0,
  `addDraw()` twice → 2.
- `<test>/ui/favdraw/FavoritesDrawViewModelTest.kt` (3): empty favorites → `Empty` and `draw()` does nothing; draw →
  `Spinning` with the chosen name at index `REEL_LEN - 1`, then `Result` and `onDrawn` received the shop; result carries
  distance from `area.center`.
- `<test>/ui/multi/MultiplayerViewModelTest.kt` (6): (1) drawing all 4 slots back to back fills all results and the search
  ran exactly once; (2) the cache is reused for later draws in the same area and refetched after `area` changes;
  (3) Favorites source never calls search and draws from favorites; (4) `canDecide` is false until all four have results,
  `decide()` then sets `winnerIndex` in 0..3 and `winner == slots[winnerIndex].result`; (5) `setSource` resets slots;
  (6) an empty nearby result sets `message = Empty` and leaves the slot not spinning.

Instrumented (stateless screens, no ViewModel):
- `<atest>/ui/multi/MultiplayerScreenTest.kt` (2): initial state shows four `multi_draw_player` buttons and `multi_decide`
  is not enabled, clicking 「玩家 3 抽」 calls `onDraw(2)`; a state with four results enables `multi_decide` and clicking it
  calls `onDecide`.
- `<atest>/ui/favdraw/FavoritesDrawScreenTest.kt` (1): `Result` state shows the shop name and `btn_detail` passes the shop
  to `onOpenDetail`.

Do not modify existing tests except where a signature you changed requires it (e.g. `FavoritesPage` gaining `onDraw`).
