# 第三段規格：抽籤頁篩選（最低星等、消費級距、營業中、餐廳類型）

Repo：Food Roulette（Kotlin、Jetpack Compose），套件 `edu.android.wut2eat`。動手前先讀 repo 根目錄的 `AGENTS.md`。這一段建立在第一、二段之上（店名精簡、詳情頁 Place Details 已完成）。

## 目標

抽籤頁（Home）加一個「篩選」按鈕，打開底部面板設定：

- **最低星等**：不限／3.5★ 以上／4.0★ 以上／4.5★ 以上（單選）。
- **消費級距**：$、$$、$$$、$$$$（可複選，都不選＝不限）。
- **營業中**：開關，開啟時只抽現在營業中的店。
- **餐廳類型**：小吃、速食、咖啡廳、早午餐（可複選，都不選＝不限，沿用現有的 `TYPES`）。

規則：

- 類型由 Google 端過濾：改 `SearchNearbyRequest.setIncludedPrimaryTypes(...)`，不額外計費。
- 星等、價位、營業中需要 Enterprise 欄位。**只有這三項至少一項開啟時**，附近搜尋才多要 `RATING`、`PRICE_LEVEL`、`CURRENT_OPENING_HOURS`、`UTC_OFFSET`；都沒開時維持現在的 Pro 欄位，以免平常抽籤也被升級計價。
- 某項篩選開啟時，缺少該項資料的店（例如沒有價位）一律排除。
- 篩選條件存在 DataStore，下次開 App 還在（比照半徑）。
- 只套用在抽籤頁。多人頁的「附近」池、收藏抽籤不變。

## 1. domain（純 Kotlin，不可引用 Android／Google SDK，不加 serialization 註解；可用 `java.time`）

### 1.1 新檔 `domain/OpeningHours.kt`

```kotlin
/** 一週中的某一刻：isoDay 1(一)..7(日)，minute 0..1439 */
data class WeekMinute(val isoDay: Int, val minute: Int)

/** 一段營業時間；close 為 null 表示 24 小時營業 */
data class OpenPeriod(val open: WeekMinute, val close: WeekMinute?)

/** 現在是否營業；沒有任何時段時回傳 null（未知） */
fun isOpenAt(periods: List<OpenPeriod>, now: WeekMinute): Boolean?

/** instant 在 UTC 偏移 utcOffsetMinutes 的時區是星期幾、幾分 */
fun weekMinuteAt(instant: java.time.Instant, utcOffsetMinutes: Int): WeekMinute
```

`isOpenAt`：periods 空 → null；任何一段 `close == null` → true；否則把 open／close 換成「一週第幾分鐘」（`(isoDay-1)*1440 + minute`），`close <= open` 表示跨週（close 加 7*1440）；`now` 落在 `[open, close)` 內（`now` 與 `now + 7*1440` 都要比）就是 true。跨夜（例如週五 18:00–週六 02:00）自然成立。

### 1.2 新檔 `domain/Filter.kt`

```kotlin
/** 抽籤頁的餐廳類型；types 是傳給 Places includedPrimaryTypes 的值 */
enum class FoodCategory(val types: List<String>) {
    SNACK(listOf("taiwanese_restaurant", "snack_bar", "noodle_shop", "dumpling_restaurant")),
    FAST_FOOD(listOf("fast_food_restaurant", "hamburger_restaurant", "chicken_restaurant")),
    CAFE(listOf("cafe", "coffee_shop")),
    BRUNCH(listOf("brunch_restaurant", "breakfast_restaurant")),
}

val MIN_RATING_OPTIONS = listOf(3.5, 4.0, 4.5)

data class ShopFilter(
    val minRating: Double? = null,               // null＝不限
    val priceLevels: Set<Int> = emptySet(),      // 1..4；空＝不限
    val openNow: Boolean = false,
    val categories: Set<FoodCategory> = emptySet(), // 空＝不限
) {
    /** 需要 Enterprise 欄位（星等、價位、營業時間）才能判斷 */
    val needsDetails: Boolean get() = minRating != null || priceLevels.isNotEmpty() || openNow
    /** 已開啟的篩選項數（星等、價位、營業中、類型各算一項） */
    val activeCount: Int get() = ...
    val isActive: Boolean get() = activeCount > 0
}

/** 一次附近搜尋要用的類型與欄位 */
data class SearchQuery(val types: List<String> = TYPES, val withDetails: Boolean = false)

fun searchQuery(filter: ShopFilter): SearchQuery
// categories 空 → TYPES；否則依 FoodCategory 宣告順序串接各類型的 types 並去重。withDetails = filter.needsDetails。

fun matchesFilter(shop: Shop, filter: ShopFilter): Boolean
// minRating 有值：shop.rating != null && shop.rating >= minRating
// priceLevels 非空：shop.priceLevel != null && shop.priceLevel in priceLevels
// openNow：shop.openNow == true
// categories 不檢查（已由 Google 端過濾）
```

### 1.3 `domain/Places.kt` 的 `Shop`

在 `note` 後面加三個欄位（都有預設值，現有呼叫不用改）：

```kotlin
/** 以下三項只在需要篩選時由附近搜尋填入，不存進 DataStore */
val rating: Double? = null,
val priceLevel: Int? = null,   // 1..4
val openNow: Boolean? = null,
```

`data/store/StoreCodec.kt` 的 `StoredShop` **不要**加這三個欄位（收藏與預訂快照不保存它們）。

### 1.4 `domain/Sample.kt`

- `typealias ShopSearch = suspend (pt: LatLon, radiusKm: Double, query: SearchQuery) -> List<Shop>`。
- `drawShop` 在最後加兩個有預設值的參數：`query: SearchQuery = SearchQuery()`、`accept: (Shop) -> Boolean = { true }`；每次查詢 `usable(search(pt, radiusKm, query), here, radiusKm).filter(accept)`。其餘邏輯（最多 `MAX_TRIES` 次）不變。
- 多人頁（`MultiplayerViewModel`、`NearbyPoolCache`）的呼叫不傳新參數，行為不變。

## 2. data

### 2.1 `data/PlacesSearch.kt`

- `suspend fun search(pt: LatLon, radiusKm: Double, query: SearchQuery): List<Shop>`：`setIncludedPrimaryTypes(query.types)`；欄位用 `if (query.withDetails) FIELDS + FILTER_FIELDS else FIELDS`；回傳 `toShops(places, Instant.now())`。
- companion 加 `FILTER_FIELDS = listOf(RATING, PRICE_LEVEL, CURRENT_OPENING_HOURS, UTC_OFFSET)`。
- `toShops(places: List<Place>, now: Instant)`：店名照第一段的 `cleanShopName`。另外填：
  - `rating`：`p.rating`，`<= 0` 視為 null。
  - `priceLevel`：`p.priceLevel`，不在 `1..4` 視為 null。
  - `openNow`：`p.currentOpeningHours?.periods` 轉成 `OpenPeriod`（`TimeOfWeek.day` 是 Places 的 `DayOfWeek`，用名稱對應 `java.time.DayOfWeek.valueOf(day.name).value`；`TimeOfWeek.time` 的 `hours*60 + minutes`；`close` 可能為 null），再 `isOpenAt(periods, weekMinuteAt(now, offset))`；`offset` 用 `p.utcOffsetMinutes`，null 時用裝置時區在 `now` 的偏移。沒有 `currentOpeningHours` 時為 null。
- 更新檔頭 KDoc：預設只取 Pro 欄位；開啟星等／價位／營業中篩選時，該次搜尋多要 `FILTER_FIELDS`，升級為 Nearby Search Enterprise 計價。

### 2.2 篩選條件儲存

- `data/store/StoreCodec.kt`：加 `@Serializable data class StoredFilter(val minRating: Double? = null, val priceLevels: List<Int> = emptyList(), val openNow: Boolean = false, val categories: List<String> = emptyList())`、`encodeFilter(ShopFilter)`、`decodeFilter(raw: String?): ShopFilter`。解碼規則：空或壞掉的 JSON → `ShopFilter()`；`minRating` 不在 `MIN_RATING_OPTIONS` → null；`priceLevels` 只留 `1..4`；`categories` 用 enum 名稱，認不得的名稱略過。
- `data/SettingsStore.kt`：加

```kotlin
interface FilterStore {
    suspend fun load(): ShopFilter
    suspend fun save(filter: ShopFilter)
}
class DataStoreFilterStore(private val dataStore: DataStore<Preferences>) : FilterStore  // key: stringPreferencesKey("filter_v1")
class MemoryFilterStore(private var value: ShopFilter = ShopFilter()) : FilterStore     // 測試與預設用
```

### 2.3 `di/AppContainer.kt`

- `val filterStore: FilterStore = DataStoreFilterStore(dataStore)`，傳給 `RouletteViewModel`。
- `create()`：有金鑰時 `search = { pt, r, q -> placesSearch.search(pt, r, q) }`（和第二段的 `details` 用同一個 `PlacesSearch` 實例）；沒金鑰時 `{ _, _, _ -> emptyList() }`。

## 3. UI

### 3.1 `ui/RouletteViewModel.kt`

- 建構子加 `private val filterStore: FilterStore = MemoryFilterStore()`（放在 `hooks` 後面）。
- `UiState` 加 `val filter: ShopFilter = ShopFilter()`。
- `init`：有金鑰時和半徑一起載入：`filterStore.load()` 後更新 `filter`。
- `fun setFilter(filter: ShopFilter)`：轉動中直接 return；更新 state、`filterStore.save`、`clearResult()`（比照 `setRadius`）。
- `spin()`：讀當下的 `filter`，`drawShop(search, here, radius, rand, searchQuery(filter)) { matchesFilter(it, filter) }`。

### 3.2 新檔 `ui/FilterSheet.kt`

- 無狀態的 `@Composable fun FilterSheetContent(filter: ShopFilter, onChange: (ShopFilter) -> Unit, modifier: Modifier = Modifier)`：由上到下
  1. 標題 `filter_title`。
  2. 「最低星等」`filter_min_rating`：`FilterChip` 單選，「不限」`filter_any` + `MIN_RATING_OPTIONS` 各一個（文字 `filter_rating_option`，例「4.0★ 以上」）。
  3. 「消費級距」`filter_price`：`FilterChip` 複選，文字為 `"$".repeat(n)`，n = 1..4。
  4. 「只抽營業中的店」`filter_open_now`：一列文字＋`Switch`。
  5. 「餐廳類型」`filter_category`：`FilterChip` 複選，`FoodCategory` 各一個（`category_snack` 小吃、`category_fast_food` 速食、`category_cafe` 咖啡廳、`category_brunch` 早午餐）。
  6. 灰色說明 `filter_note`。
  7. `TextButton`「清除篩選」`filter_clear` → `onChange(ShopFilter())`。
  - 每次點選立即呼叫 `onChange` 帶新的 `ShopFilter`。`FilterChip` 外觀比照 `ui/addshop/AddShopScreen.kt`。整個內容可垂直捲動。
- `@Composable fun FilterSheet(filter, onChange, onDismiss)`：用 Material3 `ModalBottomSheet` 包住 `FilterSheetContent`。

### 3.3 `ui/Panel.kt`

- 參數加 `onFilterChange: (ShopFilter) -> Unit = {}`。
- 在「半徑」標題列右側（`$radiusStr km` 文字之前或同一列）加一個「篩選」`TextButton`：文字 `filter_button`（未啟用）或 `filter_button_count`（「篩選（%1$d）」帶 `state.filter.activeCount`），顏色用 `colors.accent`；轉動中停用。按下以 `rememberSaveable` 的布林值打開 `FilterSheet`，`onChange = onFilterChange`，`onDismiss` 關閉。
- `Phase.Empty` 的提示文字與滾輪說明：`state.filter.isActive` 時改用 `info_empty_filtered`（帶半徑），否則維持 `info_empty`。

### 3.4 `ui/RouletteScreen.kt`

把 `onFilterChange = { viewModel.setFilter(it) }` 傳給 `Panel`。

### 3.5 字串（`strings.xml`，放在半徑字串附近）

| name | 內容 |
|---|---|
| `filter_button` | 篩選 |
| `filter_button_count` | 篩選（%1$d） |
| `filter_title` | 篩選條件 |
| `filter_min_rating` | 最低星等 |
| `filter_any` | 不限 |
| `filter_rating_option` | %1$.1f★ 以上 |
| `filter_price` | 消費級距 |
| `filter_open_now` | 只抽營業中的店 |
| `filter_category` | 餐廳類型 |
| `category_snack` | 小吃 |
| `category_fast_food` | 速食 |
| `category_cafe` | 咖啡廳 |
| `category_brunch` | 早午餐 |
| `filter_note` | 開啟星等、價位或營業中篩選時，沒有該項資料的店不會被抽到 |
| `filter_clear` | 清除篩選 |
| `info_empty_filtered` | %1$s km 內沒有符合篩選條件的店，放寬條件或拉大半徑 |

## 4. 測試

### 4.1 JVM

- `ui/RouletteViewModelTest.kt` 的 `FakeShopSearch`：`search(pt, radiusKm, query: SearchQuery)`，另加 `val queries = mutableListOf<SearchQuery>()` 記錄每次的 query；`calls` 的型別與內容不變，`customSearch` 也改成三個參數。其他用 `fakeShopSearch::search` 的測試檔因此自動跟著改；`domain/SampleTest.kt` 的 lambda 改成三個參數。
- 新增 `domain/OpeningHoursTest.kt`：一般時段內／外、跨夜（週五 18:00–週六 02:00 在週六 01:00 為 true）、跨週（週日 20:00–週一 02:00 在週一 01:00 為 true）、`close == null` 為 true、空清單為 null；`weekMinuteAt` 用固定 `Instant` 與偏移 480 驗證星期與分鐘。
- 新增 `domain/FilterTest.kt`：`matchesFilter` 每一項（含缺資料被排除、全部預設時一律通過）；`searchQuery`（沒選類型 → `TYPES` 且 `withDetails` false；選 CAFE＋BRUNCH → 兩者 types 串接；開最低星等 → `withDetails` true；只選類型 → `withDetails` false）；`activeCount`。
- `domain/SampleTest.kt`：加一個測試：`accept` 排除所有店時三次都查不到並回傳 null；`query` 原封不動傳給 search。
- `RouletteViewModelTest`：加測試：`setFilter(ShopFilter(minRating = 4.0, categories = setOf(FoodCategory.CAFE)))` 後 `spin()`，search 收到的 query 為 CAFE 的 types 且 `withDetails = true`，回傳兩間店（rating 4.5 與 3.9）時只會抽到 4.5 那間；全部不符合時 phase 為 `Empty`；`setFilter` 會寫進傳入的 `MemoryFilterStore`，新建的 VM 會讀回同一個 filter。
- `data/store/StoreCodecTest.kt`：`encodeFilter`／`decodeFilter` 來回一致；壞掉的 JSON、超出範圍的價位、認不得的類型名稱被正確處理。

### 4.2 Compose instrumentation

- `testing/TestDoubles.kt`、`ui/AppFlowTest.kt`、`ui/nav/AppNavigationTest.kt` 裡的 `ShopSearch` lambda 改成三個參數（`{ _, _, _ -> ... }`）。
- 新增 `ui/FilterSheetTest.kt`（測無狀態的 `FilterSheetContent`）：點「4.0★ 以上」→ `onChange` 收到 `minRating = 4.0`；點「咖啡廳」→ `categories` 含 `CAFE`；點「$$」→ `priceLevels` 含 2；在非預設 filter 下點「清除篩選」→ `onChange(ShopFilter())`。點擊前先 `performScrollTo()`。

## 不要做

- 不改多人頁、收藏抽籤、詳情頁、分享頁、預訂頁。
- 不改 Gradle 檔、`AGENTS.md`、`README.md`、ProGuard 規則。
- 不讀取或輸出 `local.properties`。
- 不重新排版無關程式碼。
