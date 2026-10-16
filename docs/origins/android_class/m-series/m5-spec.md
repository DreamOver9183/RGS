# Milestone M5 spec: demo booking flow + bookings list on the 我的 tab

Read `gemini-rules.md` (same folder) first and follow it strictly. Read every existing file you modify in full
first, and the code you build on: `domain/Extras.kt` (`ShopExtras`, `fakeExtras`, `formatClock`), `data/*.kt`,
`data/store/StoreCodec.kt`, `data/ShopLookup.kt`, `di/AppContainer.kt`, `ui/AppRoot.kt`, `ui/detail/*`, `ui/multi/*`,
`ui/me/*`, `ui/common/*`, and the fakes under `<test>/testing/`. Shorthands: `<main>/`, `<test>/`, `<atest>/`, `<res>/`
as before. Conventions as in previous milestones. All text in `strings.xml`. No new dependencies. Use `java.time`
(`LocalDate`, `LocalTime`, `Clock`) — available on minSdk 35 and in JVM tests.

## 1. Domain — new `<main>/domain/Booking.kt`
```kotlin
const val MIN_PARTY = 1
const val MAX_PARTY = 10
const val MAX_BOOKING_NOTE = 100
const val MAX_BOOKER_NAME = 16
/** 可預訂的日期範圍：今天起 BOOKING_DAYS 天（含今天） */
const val BOOKING_DAYS = 14
const val SLOT_STEP_MINUTES = 30

data class Booking(
    val code: String,
    val shop: Shop,            // 預訂當下的店家快照（distKm 一律 0）
    val date: LocalDate,
    val time: LocalTime,
    val party: Int,
    val name: String,
    val note: String,
    val createdAt: Long,       // epoch millis
    val cancelled: Boolean = false,
)

enum class BookingError { DateOutOfRange, ShopClosed, NoSlot, PartySize, NameRequired, NoteTooLong }

/** 某天可預訂時段：營業開始到打烊前 60 分鐘，每 30 分鐘一格；公休日為空；今天只留 now 之後的時段 */
fun bookingSlots(extras: ShopExtras, date: LocalDate, now: LocalDateTime): List<LocalTime>
/** 依序檢查（第一個錯誤即回傳）：日期範圍 → 公休/無時段 → 時段 → 人數 → 姓名 → 備註長度；全部通過回傳 null */
fun validateBooking(date: LocalDate, time: LocalTime?, party: Int, name: String, note: String,
    today: LocalDate, slots: List<LocalTime>): BookingError?
/** 不易混淆的字元 */
const val BOOKING_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
/** "FR" + 6 個字元 */
fun newBookingCode(rand: () -> Double = Math::random): String
```
Details: `bookingSlots` returns empty when `date.dayOfWeek.value == extras.closedWeekday`; slots are
`openMinute, openMinute + 30, … ≤ closeMinute − 60`; when `date == now.toLocalDate()` keep only slots strictly after
`now.toLocalTime()`. `validateBooking`: `DateOutOfRange` when date is before `today` or not before `today + BOOKING_DAYS`;
`ShopClosed` when `slots` is empty; `NoSlot` when `time == null || time !in slots`; `PartySize` outside
`MIN_PARTY..MAX_PARTY`; `NameRequired` when `name.isBlank()`; `NoteTooLong` when `note.length > MAX_BOOKING_NOTE`.

## 2. Data
1. `StoreCodec.kt`: `@Serializable data class StoredBooking(val code: String, val shop: StoredShop, val date: String /* ISO yyyy-MM-dd */, val time: String /* HH:mm */, val party: Int, val name: String = "", val note: String = "", val createdAt: Long = 0, val cancelled: Boolean = false)`
   with `encodeBookings(list)` / `decodeBookings(raw: String?): List<Booking>` (null/blank/corrupt → empty; an entry whose
   date/time cannot be parsed is skipped, not fatal).
2. New `<main>/data/BookingRepository.kt`:
   ```kotlin
   interface BookingRepository {
       /** 最新的在最前面 */
       val bookings: Flow<List<Booking>>
       suspend fun add(booking: Booking)
       suspend fun cancel(code: String)   // marks cancelled = true
   }
   class DataStoreBookingRepository(private val dataStore: DataStore<Preferences>) : BookingRepository
   ```
   Key `stringPreferencesKey("bookings_v1")`; one `edit` per mutation; same `catch`/`distinctUntilChanged` pattern.
3. `ShopLookup`: add a `bookings: BookingRepository` constructor parameter and search order registry → favorites →
   bookings' shop snapshots → `SEED_SHOPS`. Update its construction in `AppContainer` and in `<test>/data/ShopLookupTest.kt`
   (keep its existing assertions; add the new source).
4. `AppContainer`: constructor gets a trailing `clock: Clock = Clock.systemDefaultZone()` (after `appScope`);
   `val bookings: BookingRepository = DataStoreBookingRepository(dataStore)`; initializer
   `BookingViewModel(shopId = createSavedStateHandle().toRoute<BookingRoute>().shopId, lookup = shopLookup, bookings = bookings, profile = profile, clock = clock)`;
   pass `bookings` to `MeViewModel`.

## 3. Booking page — package `edu.android.wut2eat.ui.booking`
```kotlin
data class BookingUiState(
    val loading: Boolean = true,
    val notFound: Boolean = false,
    val shop: Shop? = null,
    val dates: List<LocalDate> = emptyList(),        // BOOKING_DAYS dates from today
    val closedDates: Set<LocalDate> = emptySet(),    // dates with no slots
    val date: LocalDate? = null,
    val slots: List<LocalTime> = emptyList(),
    val time: LocalTime? = null,
    val party: Int = 2,
    val name: String = "",
    val note: String = "",
    val error: BookingError? = null,
    val confirmed: Booking? = null,
)
class BookingViewModel(
    shopId: String,
    private val lookup: ShopLookup,
    private val bookings: BookingRepository,
    private val profile: ProfileRepository,
    private val clock: Clock,
    private val rand: () -> Double = Math::random,
) : ViewModel() {
    val state: StateFlow<BookingUiState>
    fun selectDate(date: LocalDate)   // recompute slots; keep time if still offered, else first slot (or null)
    fun selectTime(time: LocalTime)
    fun setParty(party: Int)          // coerceIn(MIN_PARTY, MAX_PARTY)
    fun setName(name: String)         // take(MAX_BOOKER_NAME)
    fun setNote(note: String)         // take(MAX_BOOKING_NOTE)
    fun submit()                      // validate → error, or save Booking and set confirmed
}
```
- `init`: look the shop up; not found → `notFound = true, loading = false`. Otherwise `extras = fakeExtras(shop.id)`,
  `today = LocalDate.now(clock)`, `now = LocalDateTime.now(clock)`, `dates = today … today + BOOKING_DAYS − 1`,
  `closedDates` = dates whose `bookingSlots` is empty, select the first open date and its first slot, prefill `name` with
  the profile nickname (`profile.profile.first().nickname`).
- `submit()`: ignore if `confirmed != null`; `validateBooking(...)`; on error set `error`; else create
  `Booking(code = newBookingCode(rand), shop = shop.copy(distKm = 0.0), date, time, party, name.trim(), note.trim(), createdAt = clock.millis())`,
  `bookings.add(it)`, then `confirmed = it, error = null`.

`BookingScreen(state: BookingUiState, onBack: () -> Unit, onSelectDate: (LocalDate) -> Unit, onSelectTime: (LocalTime) -> Unit, onPartyChange: (Int) -> Unit, onNameChange: (String) -> Unit, onNoteChange: (String) -> Unit, onSubmit: () -> Unit, onDone: () -> Unit, modifier: Modifier = Modifier)`
inside `SubPageScaffold(title = stringResource(R.string.booking_title), onBack)`, scrollable column, 16.dp padding, `imePadding()`:
- Loading / not found as in the detail page (`R.string.detail_loading`, `R.string.detail_not_found` + back button).
- When `confirmed != null` show ONLY a confirmation card: `FoodIcon.Calendar` icon, `R.string.booking_done_title`,
  the code (28.sp bold, letter spacing), shop name, `stringResource(R.string.booking_summary, dateText, timeText, party)`,
  the demo notice `R.string.booking_demo_notice`, and a primary button `R.string.btn_done` → `onDone`.
- Otherwise the form:
  1. Shop name (20.sp bold) + `R.string.demo_badge` chip.
  2. Section `R.string.booking_date`: a `LazyRow` of `FilterChip`s, label `stringResource(R.string.booking_date_chip, month, day, weekdayName)`
     (weekday from `R.array.weekday_names`), disabled for `closedDates`, selected = `date`.
  3. Section `R.string.booking_time`: `FlowRow` of `FilterChip`s (`HH:mm`); `R.string.booking_no_slots` when empty.
  4. Section `R.string.booking_party`: a stepper — `IconButton` "−" (contentDescription `R.string.booking_party_minus`),
     the count `stringResource(R.string.booking_party_count, party)`, `IconButton` "+" (`R.string.booking_party_plus`);
     disabled at the bounds.
  5. `OutlinedTextField` name (label `R.string.booking_name`), `OutlinedTextField` note (label `R.string.booking_note`,
     3 lines, supporting text `"${note.length}/$MAX_BOOKING_NOTE"`).
  6. Error text (colour `colors.accent`) mapped from `BookingError` to `R.string.booking_err_*`.
  7. Primary accent button `R.string.btn_confirm_booking` → `onSubmit`.
`BookingPage(onBack: () -> Unit, modifier: Modifier = Modifier)` (`onDone` = `onBack`).

Navigation: `@Serializable data class BookingRoute(val shopId: String)`; `composable<BookingRoute>`; entry points:
`DetailPage` gets an `onBook: (Shop) -> Unit` parameter forwarded to `DetailScreen.onBook`
(`AppRoot`: `navController.navigate(BookingRoute(it.id))`); the multiplayer winner card gets a `TextButton`
`R.string.btn_book` → new `MultiplayerScreen`/`MultiplayerPage` parameter `onBook: (Shop) -> Unit` (update
`MultiplayerScreenTest` call sites only as needed to compile).

New icon `<res>/drawable/ic_calendar.xml` in the same hand-drawn style (calendar outline with two rings on top);
`FoodIcon.Calendar`.

## 4. 我的 tab additions
- `MeUiState`: add `bookings: List<Booking> = emptyList()` and derived `val activeBookings: Int get() = bookings.count { !it.cancelled }`.
- `MeViewModel`: new constructor parameter `bookings: BookingRepository` (after `fakeLocation`); include it in the
  combine; add `fun cancelBooking(code: String)`.
- `MeScreen`: new parameters `onCancelBooking: (String) -> Unit` and `onOpenShop: (Shop) -> Unit` (place them before
  `modifier`; update existing call sites/tests to compile). Add a third stat card `R.string.me_stat_bookings` /
  `activeBookings`. Add a section `R.string.me_bookings` listing bookings (or `R.string.me_bookings_empty`): each card shows
  shop name (click → `onOpenShop(booking.shop)`), date/time/party via `R.string.booking_summary`, the code, and either a
  `TextButton` `R.string.btn_cancel_booking` (opens an `AlertDialog` `R.string.booking_cancel_confirm` with confirm
  `R.string.btn_cancel_booking` → `onCancelBooking(code)` and dismiss `R.string.btn_keep_booking`) or the label
  `R.string.booking_cancelled` (muted) when cancelled.
- `AppRoot`: `onOpenShop = { navController.navigate(DetailRoute(it.id)) }`.

## 5. Strings
`booking_title` 預訂, `booking_date` 日期, `booking_date_chip` %1$d/%2$d（%3$s）, `booking_time` 時段,
`booking_no_slots` 這天公休，請換一天, `booking_party` 人數, `booking_party_count` %1$d 位, `booking_party_minus` 減少人數,
`booking_party_plus` 增加人數, `booking_name` 訂位人, `booking_note` 備註（選填）, `btn_confirm_booking` 確認預訂,
`booking_err_date` 只能預訂 14 天內的日期, `booking_err_closed` 這天公休，請換一天, `booking_err_slot` 請選擇時段,
`booking_err_party` 人數需為 1–10 位, `booking_err_name` 請填寫訂位人, `booking_err_note` 備註最多 100 字,
`booking_done_title` 預訂成功！, `booking_summary` %1$s %2$s・%3$d 位, `booking_demo_notice` 這是示範預訂，不會真的通知店家。,
`btn_done` 完成, `me_stat_bookings` 有效預訂, `me_bookings` 我的預訂, `me_bookings_empty` 還沒有預訂,
`btn_cancel_booking` 取消預訂, `btn_keep_booking` 保留, `booking_cancel_confirm` 確定要取消這筆預訂嗎？, `booking_cancelled` 已取消.

## 6. Tests
JVM (add `FakeBookingRepository` to `<test>/testing/`):
- `<test>/domain/BookingRulesTest.kt` (4): slots for a weekday (first = open, last = close − 60, step 30); closed weekday →
  empty; today drops slots not after `now`; `validateBooking` returns each error in order and null when valid; plus
  `newBookingCode` = "FR" + 6 chars from the alphabet (deterministic rand) inside one of these.
- `<test>/data/DataStoreBookingRepositoryTest.kt` (2): real DataStore; add keeps newest first and round-trips every field;
  `cancel` marks only that code.
- `<test>/ui/booking/BookingViewModelTest.kt` (3) with a fixed `Clock` (`Clock.fixed(Instant.parse("2026-10-15T02:00:00Z"), ZoneId.of("Asia/Taipei"))`):
  init selects the first open date + first slot and prefills the nickname; submit with name blank → `NameRequired` and
  nothing saved; valid submit → `confirmed` set and the repository holds it.
- `<test>/ui/me/MeViewModelTest.kt`: ADD 1 test — bookings are exposed (`activeBookings` excludes cancelled) and
  `cancelBooking` cancels.
- `<test>/data/ShopLookupTest.kt`: ADD 1 test — a shop known only from a booking is found.

Instrumented:
- `<atest>/ui/booking/BookingScreenTest.kt` (2): form — clicking "+" calls `onPartyChange(party + 1)` and `btn_confirm_booking`
  calls `onSubmit`; confirmed state shows the code and `btn_done` calls `onDone`.
