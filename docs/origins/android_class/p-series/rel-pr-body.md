## 摘要

發行 v1.1.0 的版本號更新（依 AGENTS.md「Publish a release」步驟 1）。

- `versionName` 1.0.0 → **1.1.0**，`versionCode` 2 → **3**（`app/build.gradle.kts` 的 `defaultConfig`）
- 同步更新 AGENTS.md 工具鏈清單的 App version，以及 README「版本與下載」的目前版本

## 本版內容（自 v1.0.0 起）

- roccadam113/android_class#11 店名精簡：去除 Places 店名中 `|` 之後的宣傳字樣
- roccadam113/android_class#12 詳情頁顯示 Google 真實店家資訊（Place Details），並新增電話訂餐
- roccadam113/android_class#13 抽籤頁篩選：最低星等、消費級距、只抽營業中、餐廳類型

## 合併之後

從合併 commit 執行 `assembleDebug` 建置 APK，改名為 `food-roulette-v1.1.0.apk`，發布到 `v1.1.0` GitHub Release。本 PR 不建立 tag 或 Release。

## 測試

- [x] `./gradlew assembleDebug` 建置成功

🤖 Generated with [Claude Code](https://claude.com/claude-code)
