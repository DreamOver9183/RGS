# 第一段規格：精簡 Places 店名

Repo：Food Roulette（Kotlin、Jetpack Compose），套件 `edu.android.wut2eat`。動手前先讀 repo 根目錄的 `AGENTS.md`。

## 目標

Google 地圖上不少店家把宣傳字詞塞進店名，例如：

```
SIX STAR 六星炸雞(勤美英才店) ft.卜蜂商店 |台中美食|必吃炸雞|炸物推薦
```

App 只顯示核心店名：

```
SIX STAR 六星炸雞(勤美英才店) ft.卜蜂商店
```

## 1. domain：新增 `cleanShopName`

新檔 `app/src/main/java/edu/android/wut2eat/domain/ShopName.kt`（純 Kotlin，不可引用 Android 或 Google SDK，不可加 serialization 註解）：

- 分隔符號常數 `NAME_SEPARATORS`：`'|'`（U+007C）、`'｜'`（U+FF5C）、`'丨'`（U+4E28）、`'│'`（U+2502）。
- `fun cleanShopName(raw: String): String`：
  1. 找第一個分隔符號，取它之前的字，再 `trim()`。
  2. 沒有分隔符號：回傳 `raw.trim()`。
  3. 步驟 1 的結果是空字串（例如以分隔符號開頭的 `|台中美食`）：回傳 `raw.trim()`，不要回傳空字串。
- 只處理上面四個分隔符號。不要動 `-`、`–`、`【】`、`()`、`ft.` 等符號，真實店名常含這些。
- 加一行中文 KDoc 說明用途，風格比照同目錄其他檔案。

## 2. 套用位置

1. `app/src/main/java/edu/android/wut2eat/data/PlacesSearch.kt` 的 `toShops`：`name = cleanShopName(name)`。精簡後若是空白字串（`displayName` 只有空白），略過這間店（`mapNotNull` 回傳 null），和缺 `displayName` 時一樣。
2. `app/src/main/java/edu/android/wut2eat/data/store/StoreCodec.kt` 的 `StoredShop.toShop()`：已存在手機上的 Places 店家（收藏、預訂快照）讀出時也精簡店名。只對 Places 店家做；id 以 `CUSTOM_ID_PREFIX`（`custom:`）或 `SEED_ID_PREFIX`（`seed:`）開頭的店維持原名，因為使用者自訂的店名可能刻意含 `|`。判斷方式沿用 `domain/ShopIds.kt` 的 `isPlacesShop` 邏輯（可先建出 `Shop` 再依 `isPlacesShop` 決定，或直接比對前綴，擇一，不要複製一份新的判斷規則）。不回寫 DataStore。

## 3. 測試（JVM，`app/src/test/`）

1. 新增 `app/src/test/java/edu/android/wut2eat/domain/ShopNameTest.kt`，至少涵蓋：
   - 上面的範例字串精簡成 `SIX STAR 六星炸雞(勤美英才店) ft.卜蜂商店`。
   - 全形 `｜` 與 `丨` 也會切。
   - 沒有分隔符號的店名不變，包含含有 `-`、`【】`、`(…)` 的店名。
   - 以分隔符號開頭的 `|台中美食` 回傳原字串（trim 後）。
   - 前後空白會去掉：`"  拉麵 屋  | 宣傳"` → `"拉麵 屋"`。
2. 在 `app/src/test/java/edu/android/wut2eat/data/store/StoreCodecTest.kt` 加一個測試：用 `encodeShops` 存三間店再 `decodeShops`：
   - Places 店（id 例如 `ChIJxxxx`）的長店名讀出後已精簡。
   - `custom:` 店名含 `|` 時維持原樣。
   - `seed:` 店名維持原樣。
3. 不要為 `toShops` 寫需要 Places SDK `Place` 物件的 JVM 測試。

測試命名與斷言風格比照同目錄現有測試（JUnit4、`testXxx_yyy` 或現有寫法）。

## 不要做

- 不改任何 UI、字串資源、Gradle 檔、`AGENTS.md`、`README.md`。
- 不改其他行為，不重新排版無關程式碼。
- 不讀取或輸出 `local.properties`。
