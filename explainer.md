# Economics explainer: what this tracker's data shows

This page explains the pattern in the tracker's price data and why it looks
the way it does. All numbers below are computed directly from the seeded
database (run `python analyze.py` to reproduce them).

## The headline

Over the whole window (January 2023 → late 2026), the **equal-weight basket of
28 everyday goods rose about +121% in PKR**, an average of roughly **25% per
year**. That is fast inflation — a shopper who needed `Rs 16,013` to fill the
basket in January 2023 would need about `Rs 35,324` in 2026 to buy the same
things. Prices broadly **doubled** in three and a half years.

The steepest cumulative rises were in:

| Item | Start → Latest | Cumulative |
|---|---|---|
| Tea (packed) | `Rs 1,950` → `Rs 5,209` / kg | **+167%** |
| Electricity | `Rs 35` → `Rs 87` / kWh | **+151%** |
| Petrol (super) | `Rs 271` → `Rs 637` / litre | **+135%** |
| Beef | `Rs 862` → `Rs 2,005` / kg | **+133%** |
| Diesel (high speed) | `Rs 296` → `Rs 676` / litre | **+128%** |
| Vegetable ghee | `Rs 612` → `Rs 1,388` / kg | **+127%** |
| Yogurt (curd) | `Rs 203` → `Rs 459` / kg | **+126%** |
| Gram lentil (chana daal) | `Rs 271` → `Rs 608` / kg | **+124%** |
| Wheat flour (atta) | `Rs 1,950` → `Rs 4,361` / 20 kg bag | **+124%** |
| Sugar | `Rs 157` → `Rs 352` / kg | **+124%** |
| Gram flour (besan) | `Rs 280` → `Rs 622` / kg | **+122%** |
| Mutton | `Rs 2,390` → `Rs 5,240` / kg | **+119%** |
| Eggs | `Rs 343` → `Rs 742` / dozen | **+117%** |
| LPG | `Rs 263` → `Rs 564` / kg | **+115%** |
| Masoor lentil | `Rs 292` → `Rs 627` / kg | **+114%** |
| Mash lentil | `Rs 443` → `Rs 949` / kg | **+114%** |
| Cooking oil | `Rs 2,487` → `Rs 5,226` / 5 L | **+110%** |
| Ginger | `Rs 402` → `Rs 844` / kg | **+110%** |
| Basmati rice | `Rs 216` → `Rs 453` / kg | **+110%** |
| Fresh milk | `Rs 228` → `Rs 475` / litre | **+108%** |
| Rice (Irri-6) | `Rs 170` → `Rs 353` / kg | **+108%** |
| Chicken | `Rs 598` → `Rs 1,177` / kg | **+97%** |
| Onion | `Rs 125` → `Rs 242` / kg | **+94%** |
| Apple | `Rs 270` → `Rs 515` / kg | **+91%** |
| Banana | `Rs 163` → `Rs 309` / dozen | **+89%** |
| Garlic | `Rs 526` → `Rs 937` / kg | **+78%** |
| Potato | `Rs 67` → `Rs 107` / kg | **+59%** |
| Tomato | `Rs 141` → `Rs 156` / kg | **+11%** |

## Why inflation is high at the start and cools later — the arc

If you use the date filters to look at **2023–2024**, the lines are steep; the
same scale from **2025 onwards** is flatter. That shape is not an accident — it
mirrors Pakistan's real inflation narrative:

1. **2022–2023: price-shock stacking.** Widespread 2022 floods destroyed part
   of the cotton, rice, onion and potato harvests; the rupee depreciated sharply
   against the dollar (raising the PKR cost of imported inputs, edible oil and
   fuel); and electricity tariffs were re-based to recover system costs. All of
   this pushed **food and energy prices** up together, so the *level* of prices
   ratchets up quickly — this is what the steep 2023 part of every line shows.

2. **2024: still high but easing.** Headline CPI stayed in double digits, but
   the pace slowed as the initial shock effects started to drop out of the
   year-on-year comparison and the central bank raised interest rates to cool
   demand. The chart's slopes begin to flatten.

3. **2025–2026: disinflation.** Once the base of prices had already doubled,
   new *percentage* increases became much smaller even while prices stayed at
   their new, higher level. The tracker shows little net rise in this window —
   that is **falling inflation (disinflation), not falling prices**.

> A key economic idea: inflation is the **rate of change** of prices, not the
> price level. A high starting shock lifts prices and then *yields a high
> inflation reading for about a year* (the base effect). As the base rolls off,
> the same elevated price level can coexist with low inflation. This is why the
> chart and a "CPI % y/y" line can tell different stories at a glance.

## Energy rises most, and pulls everything up

Electricity +151% and petrol +135% grew the most. Energy sits *behind* almost
everything: fuel is used to transport, store and process food, and electricity
powers retail refrigeration and mills. When energy prices jump, they ripple
through the whole basket — which is one reason the *food* items also rose ~100%
or more even when their own harvests were normal. This is an example of a
**cost-push (supply-side) inflation channel**.

## Fresh produce is the volatile one — why alerts go off

In the alert panel, jumps cluster around **onion and potato**. Their prices do
not rise in a smooth line like rice or petrol; they move in sharp seasonal
zig-zags. The reasons are structural:

- **Harvest timing.** Right after harvest, supply is abundant and prices drop;
  a few months later stocks run down and prices spike.
- **Perishability.** They cannot be stored long, so there is little buffer
  between a bad yield and a price spike (breadth of supply risk).
- **Import dependence in lean months** (onions are imported when the local crop
  is short, exposing the price to the exchange rate and border logistics).

So a **week-on-week jump of +30% for potatoes is mostly a supply/season
signal**, not a sign that general inflation has re-accelerated. Modeling that
distinction correctly is exactly why an inflation tracker should look at *both*
the trend (smooth, sticky prices) and the one-week shocks (volatile items).

## A cookbook reading: what this means for a household

If you sum the items in the "drivers" view you see where the pressure is:

- **Sticky, steady risers** (atta, sugar, rice, oil, milk, chicken): reflect
   *underlying* inflation — the burden falls on feeding a family, and it does
   not bounce back. These are the items to watch for persistent hardship.
- **Spiky, mean-reverting items** (onion, potato): cause short-run "scarcity
   shocks" that make specific weeks feel brutal but do not push the whole
   basket permanently higher.

Governments respond to the former with income/price support and to the latter
with trade measures (imports, market stabilisation). Economic analysts
typically strip out the volatile food-and-energy components and watch a "core"
measure to judge whether the trend is genuinely cooling — which, on this data,
it is by 2025–26.

---

*Numbers reproduced with `python analyze.py` against `data/inflation.db`.
This is a representative educational dataset; the shape (high inflation
easing to disinflation, volatile fresh produce, high energy pass-through)
follows Pakistan's real CPI experience rather than being a precise official
series.*