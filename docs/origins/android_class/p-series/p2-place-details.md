# 第二段規格：詳情頁改用 Google 真實資料＋電話訂餐

Repo：Food Roulette（Kotlin、Jetpack Compose），套件 `edu.android.wut2eat`。動手前先讀 repo 根目錄的 `AGENTS.md`，尤其是架構分層、"Add a screen"、"Testing strategy"。

## 背景與目標

詳情頁現在對所有店家都顯示 `fakeExtras()` 產生的假資料（星等、價位、營業時間、介紹、招牌菜），和真實店家不符。改成：

- **Google 地圖上的店家**（`Shop.isPlacesShop == true`）：開啟詳情頁時呼叫一次 Places SDK 的 Place Details（`fetchPlace`），顯示真實的星等、價位、營業時間、店家介紹（`editorialSummary`）、供餐資訊（內用、外帶等）與電話。某項沒有資料時，該區塊顯示「Oops，店家沒有提供該資訊」，不可以拿假資料補。不顯示「示範資料」標籤。
- **示範店（`seed:`）與自訂店（`custom:`）**：維持現在的示範資料畫面（示範資料標籤、假星等、假營業時間、假介紹、假招牌菜），也不呼叫 Places。
- 詳情頁底部的「預訂」按鈕改成「電話訂餐」：有電話時按下去開啟系統撥號畫面並帶入號碼（`Intent.ACTION_DIAL`，不需要 `CALL_PHONE` 權限）；沒有電話時按鈕停用。
- **不改**多人決勝卡片的「預訂」、預訂頁、「我的」頁的預訂清單；它們照舊使用示範預訂。

## 1. domain（純 Kotlin，不可引用 Android／Google SDK，不加 serialization 註解）

新檔 `app/src/main/java/edu/android/wut2eat/domain/PlaceDetails.kt`：

```kotlin
/** 詳情頁「供餐資訊」可能出現的項目；顯示順序即宣告順序 */
enum class PlaceService { DINE_IN, TAKEOUT, DELIVERY, BREAKFAST, BRUNCH, LUNCH, DINNER, VEGETARIAN, COFFEE, DESSERT, BEER, WINE }

/** Place Details 取回的真實店家資料；null／空清單表示店家沒有提供 */
data class PlaceDetails(
    val phone: String? = null,
    val rating: Double? = null,
    val ratingCount: Int? = null,
    val priceLevel: Int? = null,      // 1..4，對應 $..$$$$
    val hours: List<String> = emptyList(), // 每天一行的營業時間文字（Places 已依語系排好）
    val summary: String? = null,      // editorialSummary
    val services: List<PlaceService> = emptyList(),
)
```

在 `app/src/main/java/edu/android/wut2eat/domain/Format.kt` 加：

- `fun telUri(phone: String): String?`：只保留數字與開頭的 `+`，組成 `tel:` 開頭的字串；沒有任何數字時回傳 null。例：`"04 2328 0080"` → `"tel:0423280080"`，`"+886 4 2328 0080"` → `"tel:+886423280080"`，`""`、`"無"` → null。

## 2. data

### 2.1 `app/src/main/java/edu/android/wut2eat/data/PlaceDetailsSource.kt`（新檔）

```kotlin
fun interface PlaceDetailsSource {
    /** 取得一間 Places 店家的詳細資料；任何失敗都丟例外 */
    suspend fun fetch(placeId: String): PlaceDetails
}
```

同檔加 `class CachedPlaceDetails(private val source: PlaceDetailsSource, private val capacity: Int = 100) : PlaceDetailsSource`：行程內 LRU 快取，同一個 id 成功取得後不再呼叫 `source`；失敗（例外）不快取，例外照樣往外丟。執行緒安全的寫法比照 `data/Session.kt` 的 `ShopRegistry`（`@Synchronized` + access-order `LinkedHashMap`）；呼叫 `source.fetch` 時不要持有鎖。

### 2.2 `app/src/main/java/edu/android/wut2eat/data/PlacesSearch.kt`

- 加 `suspend fun details(placeId: String): PlaceDetails`：`client.fetchPlace(FetchPlaceRequest.newInstance(placeId, DETAIL_FIELDS)).await().place`，再轉成 `PlaceDetails`。
- companion 加 `DETAIL_FIELDS`：`NATIONAL_PHONE_NUMBER`、`RATING`、`USER_RATING_COUNT`、`PRICE_LEVEL`、`CURRENT_OPENING_HOURS`、`OPENING_HOURS`、`EDITORIAL_SUMMARY`、`DINE_IN`、`TAKEOUT`、`DELIVERY`、`SERVES_BREAKFAST`、`SERVES_BRUNCH`、`SERVES_LUNCH`、`SERVES_DINNER`、`SERVES_VEGETARIAN_FOOD`、`SERVES_COFFEE`、`SERVES_DESSERT`、`SERVES_BEER`、`SERVES_WINE`。
- companion 加 `fun toDetails(place: Place): PlaceDetails`，規則：
  - `phone`：`nationalPhoneNumber`，空白視為 null。
  - `rating`：`rating`，`<= 0` 或 null 視為 null；`ratingCount`：`userRatingCount`。
  - `priceLevel`：`priceLevel`，不在 `1..4` 視為 null。
  - `hours`：`currentOpeningHours?.weekdayText`，空的話改用 `openingHours?.weekdayText`，都沒有就空清單。
  - `summary`：`editorialSummary`，空白視為 null。
  - `services`：各欄位等於 `Place.BooleanPlaceAttributeValue.TRUE` 的項目，依 `PlaceService` 宣告順序（`DINE_IN`←`dineIn`、`TAKEOUT`←`takeout`、`DELIVERY`←`delivery`、`BREAKFAST`←`servesBreakfast`、`BRUNCH`←`servesBrunch`、`LUNCH`←`servesLunch`、`DINNER`←`servesDinner`、`VEGETARIAN`←`servesVegetarianFood`、`COFFEE`←`servesCoffee`、`DESSERT`←`servesDessert`、`BEER`←`servesBeer`、`WINE`←`servesWine`）。
- 更新檔頭 KDoc：附近搜尋仍只取 Pro 欄位；`details` 只在開啟 Places 店家的詳情頁時呼叫，含 `editorialSummary` 與 `serves*` 屬 Enterprise + Atmosphere 計價，結果由 `CachedPlaceDetails` 在行程內快取。

### 2.3 `app/src/main/java/edu/android/wut2eat/di/AppContainer.kt`

- 建構子加參數 `placeDetailsSource: PlaceDetailsSource = PlaceDetailsSource { throw IllegalStateException("Place Details unavailable") }`（放在 `newId` 後面，讓 androidTest 的 `testContainer` 不用改也能編譯）。
- 屬性 `val placeDetails: PlaceDetailsSource = CachedPlaceDetails(placeDetailsSource)`。
- `create()`：有金鑰時把同一個 `PlacesSearch` 實例的 `details` 傳進 `placeDetailsSource`（例如 `PlaceDetailsSource { placesSearch.details(it) }`）；沒金鑰時用預設值（一律失敗）。
- `DetailViewModel` 的 initializer 多傳 `details = placeDetails`。

## 3. UI

### 3.1 `ui/detail/DetailUiState.kt`

```kotlin
sealed interface DetailInfo {
    data object Loading : DetailInfo
    data object Failed : DetailInfo
    data class Places(val details: PlaceDetails) : DetailInfo
    data class Demo(val extras: ShopExtras) : DetailInfo
}
```

`DetailUiState.Loaded` 改成 `Loaded(shop: Shop, distKm: Double, isFavorite: Boolean, info: DetailInfo)`（拿掉 `extras`）。

### 3.2 `ui/detail/DetailViewModel.kt`

- 建構子加 `private val details: PlaceDetailsSource`（放最後）。
- 店家找不到 → `NotFound`，不呼叫 `details`。
- 店家不是 Places 店（`!shop.isPlacesShop`）→ `info = DetailInfo.Demo(fakeExtras(shop.id))`，不呼叫 `details`。
- Places 店 → `info` 先是 `Loading`，呼叫 `details.fetch(shop.id)`：成功 → `Places(result)`；任何例外 → `Failed`（`CancellationException` 要重新丟出，不可吞掉）。
- `fun retryInfo()`：只有 `info` 是 `Failed` 時才動作：設回 `Loading` 再呼叫一次 `details.fetch`。
- `state` 用 `combine` 把收藏、區域距離與 `info` 組成 `Loaded`；`toggleFavorite()` 不變。整個 VM 只會在開頁時呼叫一次 `fetch`（加上使用者按重試的次數）。

### 3.3 `ui/detail/DetailScreen.kt`

參數：拿掉 `onBook`，加 `onCall: (String) -> Unit = {}`（參數是店家電話原字串）與 `onRetryInfo: () -> Unit = {}`。

`Loaded` 畫面由上到下：

1. 店名、類型・距離：不變。
2. 依 `info`：
   - `Demo`：維持現在的內容與順序（示範資料標籤、星等與價位、營業時間與公休、店家介紹、招牌菜），資料改從 `info.extras` 取。
   - `Loading`：一行灰色 `detail_loading`（既有字串「載入中…」）。
   - `Failed`：一行灰色 `detail_info_failed`，下方一個 `OutlinedButton`（樣式比照頁面其他按鈕），文字用既有的 `btn_retry`，按下呼叫 `onRetryInfo`。
   - `Places`（不顯示示範資料標籤）：
     - 星等與價位列：`rating` 有值時顯示「★ 4.5（1352 則評論）」（`ratingCount` 有值用既有 `detail_rating`，沒有用新字串 `detail_rating_only`「★ %1$.1f」）；`priceLevel` 有值時顯示「價位 $$」（既有 `detail_price` 加 `$` 重複 `priceLevel` 次）。兩者都沒有時，這一列改成一行 `detail_no_info`。
     - 「營業時間」區：標題 `detail_hours_label`；內容為 `hours` 每一行一個 `Text`；空清單時顯示 `detail_no_info`。
     - 「店家介紹」區：標題用既有 `detail_intro_label`；內容為 `summary`，null 時顯示 `detail_no_info`。
     - 「供餐資訊」區：標題 `detail_services_label`；內容為 `services` 的 chip（外觀比照現有招牌菜 chip），文字對應下方 `service_*` 字串；空清單時顯示 `detail_no_info`。
   - 區塊標題、內文的字級與顏色比照現有的「店家介紹」區。`detail_no_info` 用 `colors.muted`、14.sp。
3. 自訂店的「備註」區：不變。
4. 按鈕區：收藏、在 Google Maps 開啟：不變。原本「預訂」的位置改成「電話訂餐」按鈕（外觀比照原本預訂按鈕）：
   - `info` 是 `Places` 且 `details.phone != null`：可按，文字 `btn_call_order_number`（「電話訂餐 %1$s」帶入電話），按下呼叫 `onCall(phone)`。
   - 其他情況：`enabled = false`，文字 `btn_call_order`（「電話訂餐」）。`info` 是 `Places` 或 `Demo` 時，按鈕正下方再加一行灰色 `detail_no_info`；`Loading`、`Failed` 時不加。
   - 分享按鈕：不變。

### 3.4 串接

- `ui/detail/DetailPage.kt`：拿掉 `onBook`，加 `onCall: (String) -> Unit = {}`，傳給 `DetailScreen`；`onRetryInfo = { vm.retryInfo() }`。
- `ui/AppRoot.kt`：`FoodRouletteRoot` 加參數 `onDial: (String) -> Unit = {}`（放在 `onShareText` 後）；`DetailRoute` 目的地拿掉 `onBook`，改傳 `onCall = onDial`。多人頁 `MultiplayerPage` 的 `onBook` 與 `BookingRoute` 目的地不動。
- `MainActivity.kt`：加 `private fun dial(phone: String)`：`telUri(phone)` 為 null 時顯示 `dial_no_app` toast 後返回；否則 `startActivity(Intent(Intent.ACTION_DIAL, uri.toUri()))`，丟例外時顯示 `dial_no_app` toast（寫法比照 `shareText`）。`FoodRouletteRoot(..., onDial = ::dial)`。不要加任何權限到 Manifest。

### 3.5 字串（`app/src/main/res/values/strings.xml`，放在詳情頁相關字串附近）

| name | 內容 |
|---|---|
| `btn_call_order` | 電話訂餐 |
| `btn_call_order_number` | 電話訂餐 %1$s |
| `detail_no_info` | Oops，店家沒有提供該資訊 |
| `detail_info_failed` | 暫時無法取得店家資訊 |
| `detail_rating_only` | ★ %1$.1f |
| `detail_hours_label` | 營業時間 |
| `detail_services_label` | 供餐資訊 |
| `dial_no_app` | 找不到可撥號的應用程式 |
| `service_dine_in` | 內用 |
| `service_takeout` | 外帶 |
| `service_delivery` | 外送 |
| `service_breakfast` | 早餐 |
| `service_brunch` | 早午餐 |
| `service_lunch` | 午餐 |
| `service_dinner` | 晚餐 |
| `service_vegetarian` | 素食 |
| `service_coffee` | 咖啡 |
| `service_dessert` | 甜點 |
| `service_beer` | 啤酒 |
| `service_wine` | 葡萄酒 |

`btn_book` 保留（多人決勝卡片與預訂頁仍在用）。

## 4. 測試

### 4.1 JVM（`app/src/test/`）

- 新增 `testing/FakePlaceDetailsSource.kt`：記錄每次 `fetch` 的 id（`calls: List<String>`）；可設定依序回傳的結果（`PlaceDetails` 或例外），沒設定時回傳 `PlaceDetails()`。
- `ui/detail/DetailViewModelTest.kt`：所有 `DetailViewModel(...)` 加上 fake。修改／新增：
  - 既有 found 測試（id `shop_detail_01` 是 Places id）：`info` 為 `DetailInfo.Places(預設的 details)`，fake 被呼叫一次且 id 正確。
  - 示範店 `seed:01`：`info == DetailInfo.Demo(fakeExtras("seed:01"))`，fake 從未被呼叫。
  - 找不到的 id：`NotFound`，fake 從未被呼叫。
  - 第一次 `fetch` 丟例外 → `Failed`；`retryInfo()` 後第二次成功 → `Places(...)`，fake 共被呼叫兩次。
  - 既有的收藏切換測試保持通過。
- 新增 `data/CachedPlaceDetailsTest.kt`：同一 id 呼叫兩次，底層只被呼叫一次且結果相同；底層第一次丟例外時例外會往外丟，下一次呼叫會再打底層；不同 id 各呼叫一次。
- `domain/FormatTest.kt`：加 `telUri` 的測試（上面四個例子）。
- 不要寫需要 Places SDK `Place` 物件的 JVM 測試（`toDetails` 不測）。

### 4.2 Compose instrumentation（`app/src/androidTest/`）

- `ui/detail/DetailScreenTest.kt`：
  - 既有 loaded 測試改用 `info = DetailInfo.Demo(fakeExtras(shop.id))`，原有斷言（店名、示範資料、介紹、收藏按鈕）照舊。
  - 新增：`info = DetailInfo.Places(PlaceDetails(phone = "04 2328 0080", rating = 4.5, ratingCount = 1352, summary = null, services = listOf(PlaceService.DINE_IN)))` → 不顯示示範資料標籤；顯示 `btn_call_order_number` 帶電話的文字且可按，按下 `onCall` 收到 `"04 2328 0080"`；`detail_no_info` 至少出現一次（店家介紹）；顯示 `service_dine_in`。
  - 新增：`Places(PlaceDetails())`（全部沒有）→ 「電話訂餐」按鈕 `assertIsNotEnabled()`。
  - 可捲動畫面：檢查或點擊前一律 `performScrollTo()`（見 AGENTS.md Testing strategy）。
- `ui/AppFlowTest.kt`：
  - 原本用 `R.string.btn_book` 判斷「在詳情頁」的地方，全部改用 `R.string.btn_call_order`（示範店的詳情頁顯示停用的「電話訂餐」）。
  - 測試 1 `favoritesDraw_opensDetail_andBookingAppearsOnMe` 改名為 `favoritesDraw_opensDetail_withCallOrderDisabled`：收藏 → 從收藏抽 → 抽一間 → 詳情 → 斷言「電話訂餐」按鈕 `assertIsNotEnabled()` → 用頂部返回鍵回到收藏分頁（照現有的等待寫法）。拿掉預訂部分。
  - 新增測試 `multiplayerWinner_bookingAppearsOnMe`，把端到端預訂覆蓋移到多人頁：底部「多人」分頁 → 點 `multi_source_favorites` chip（收藏池，不需 Places）→ 依序按 `multi_draw_player` 1–4，每按一個就等該玩家結果出現（或等到下一步可行）→ 等 `multi_decide` 可按後按下 → 等決勝卡片出現（`multi_winner` 開頭的文字，或決勝卡片上的 `btn_book`）→ 按決勝卡片的 `btn_book` → 在預訂頁填 `booking_name`、按 `btn_confirm_booking` → 從 `container.bookings` 讀出預訂碼並確認畫面顯示 → 按 `btn_done`（或預訂完成頁既有的完成按鈕字串）回到多人頁 → 點「我的」分頁 → 確認列出該預訂碼。照 AGENTS.md 的規則：每次會換頁的點擊後 `waitForIdle()` 再 `waitUntil` 目標頁獨有的節點；可捲動畫面先 `performScrollTo()`。實作前先讀 `MultiplayerScreen.kt`、`BookingScreen.kt`、`MeScreen.kt` 確認實際的字串與按鈕。

## 不要做

- 不改附近搜尋的 `FIELDS`、`SearchNearbyRequest`、`ShopSearch` 型別或抽籤流程（那是下一段）。
- 不改預訂頁、多人頁、分享頁、「我的」頁的行為。
- 不改 Gradle 檔、`AGENTS.md`、`README.md`、ProGuard 規則。
- 不讀取或輸出 `local.properties`。
- 不重新排版無關程式碼。
