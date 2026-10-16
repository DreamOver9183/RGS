## Summary

Milestone M6: the "write a restaurant location" page and the share page.

- **新增餐廳** (`AddShopRoute`): name (required, ≤ 40), type chips from `SHOP_TYPES` (required), optional address/note (≤ 100), and a position from a station preset, a map tap, or 目前位置 (honours the fake location). Errors clear per field; a double tap on save cannot create two shops. Saving writes the custom shop **and** the favorite in one DataStore `edit` (`custom_shops_v1` + `favorites_v1`), then opens the new shop's detail page and pops the add page. Entry points: 收藏 header 新增 (also when the list is empty) and the 我的 新增餐廳 row.
- **分享餐廳** (`ShareRoute(shopId)`): preview card (nickname, name, type, demo rating, note ≤ 60, Maps link), 分享給朋友 → `ACTION_SEND` chooser from `MainActivity` (toast when no app), 複製連結 → clipboard. Entry points: Home result row share icon, detail page 分享, multiplayer winner card 分享 (buttons now sit below the winner name so it is not squeezed on narrow phones).
- `ShopLookup` order: registry → favorites → custom shops → booking snapshots → seed shops. `StoreKeys` holds keys shared by several repositories. `AppContainer` gains `customShops` and an injectable `newId`.
- `LocationPicker(onMapTouch = …)` reports a finger on the map so a scrollable parent can stop scrolling while the map is dragged.
- Lint `ModifierParameter` fixed in `MeScreen`/`MultiplayerScreen`; stray blank lines removed.
- AGENTS.md / README updated (structure, flows, persistence key, tests, new "map in a scrollable page" recipe).

## Testing

- `testDebugUnitTest`: 115 tests / 36 classes, all green (new: new-shop validation, custom-shop repository on a real DataStore, add-shop ViewModel incl. double tap and per-field error clearing, share ViewModel, ShopLookup custom shop).
- `lintDebug`: 0 errors (9 pre-existing build/manifest warnings). `assembleDebug` and `assembleRelease` (R8) pass.
- `connectedDebugAndroidTest`: 22 tests / 12 classes green on both a 720x1280 / 320 dpi display (like CI) and the normal emulator display.
- Manual smoke on the emulator: add restaurant (errors, preset, map drag pans the map instead of scrolling), save → detail → back to 收藏 with the shop first; share page preview/note/copy/system share sheet; favorites draw picks the custom shop; multiplayer 收藏 pool → 決勝 → 分享; Home result row share icon; 我的 新增餐廳 row.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
