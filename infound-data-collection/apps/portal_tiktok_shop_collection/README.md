# `portal_tiktok_shop_collection`

This app is a manual-login Playwright bootstrapper for seller/shop pages. The current implementation supports the same outreach-filter snapshot flow for regions that share the same affiliate page structure, currently including Mexico (`MX`), Vietnam (`VN`), Indonesia (`ID`), Brazil (`BR`), and France (`FR`).

Region-specific crawl logic now lives in separate app-local scripts:

- `scripts/outreach_filter_mx.py`
- `scripts/outreach_filter_vn.py`
- `scripts/outreach_filter_id.py`
- `scripts/outreach_filter_br.py`
- `scripts/outreach_filter_fr.py`
- shared selector/module definitions: `scripts/outreach_filter_base.py`

## Current behavior

When started, the app will:

1. Open Chromium with the configured seller account entry URL.
2. Wait for manual login.
3. After login is detected, jump to:

```text
https://affiliate.tiktok.com/connection/creator?shop_region=<REGION>
```

4. Open the outreach filter page and capture the current filter structure for:
   - `creatorFilters`
   - `followerFilters`
   - `performanceFilters`
5. Save a JSON snapshot that includes:
   - module titles
   - filter titles
   - visible options
   - input/checkbox metadata
   - button/preset texts when present
   - DSL binding hints aligned with `infound-desktop-client-master/apps/frontend.rpa.simulation/src/main/modules/rpa/outreach/support.ts`
6. Export a DB-ready `creator_filter_items` JSON that keeps the DSL bindings and also lists all captured filter option items, presets, and toggle items per filter.

The JSON snapshot is written to:

```text
apps/portal_tiktok_shop_collection/data/outreach-filter-snapshots/
```

Each capture now produces two files in the same directory:

- `outreach_filters_<region>_<account>_<timestamp>.json`: raw page capture
- `creator_filter_items_<region>_<account>_<timestamp>.json`: normalized export for the `creator_filter_items` table field

## Default startup

`dev.yaml` defaults to `MX_LOCAL_SHOP`, so the usual startup command is:

```bash
cd /Users/samxie/Research/Infound_Influencer/InFound_Back/infound-data-collection
export SERVICE_NAME=portal_tiktok_shop_collection
poetry run python main.py --consumer portal_tiktok_shop_collection --env dev
```

For Vietnam local shop, a dedicated `vn.yaml` is available:

```bash
cd /Users/samxie/Research/Infound_Influencer/InFound_Back/infound-data-collection
export SERVICE_NAME=portal_tiktok_shop_collection
env DEBUG=false poetry run python main.py --consumer portal_tiktok_shop_collection --env vn
```

For Indonesia local shop, a dedicated `id.yaml` is available:

```bash
cd /Users/samxie/Research/Infound_Influencer/InFound_Back/infound-data-collection
export SERVICE_NAME=portal_tiktok_shop_collection
env DEBUG=false poetry run python main.py --consumer portal_tiktok_shop_collection --env id
```

For Brazil local shop, a dedicated `br.yaml` is available:

```bash
cd /Users/samxie/Research/Infound_Influencer/InFound_Back/infound-data-collection
export SERVICE_NAME=portal_tiktok_shop_collection
env DEBUG=false poetry run python main.py --consumer portal_tiktok_shop_collection --env br
```

For France local shop, a dedicated `fr.yaml` is available:

```bash
cd /Users/samxie/Research/Infound_Influencer/InFound_Back/infound-data-collection
export SERVICE_NAME=portal_tiktok_shop_collection
env DEBUG=false poetry run python main.py --consumer portal_tiktok_shop_collection --env fr
```

## Choose another account

Set `SHOP_COLLECTION_BOOTSTRAP_ACCOUNT_NAME` before startup:

```bash
export SHOP_COLLECTION_BOOTSTRAP_ACCOUNT_NAME=MX_LOCAL_SHOP
poetry run python main.py --consumer portal_tiktok_shop_collection --env dev
```

If you want Vietnam cross-border instead, override the account name on top of `--env vn`:

```bash
export SHOP_COLLECTION_BOOTSTRAP_ACCOUNT_NAME=VN_CROSS_BORDER_SHOP
env DEBUG=false poetry run python main.py --consumer portal_tiktok_shop_collection --env vn
```

Configured account names currently include:

- `MX_LOCAL_SHOP`
- `VN_LOCAL_SHOP`
- `VN_CROSS_BORDER_SHOP`
- `ID_LOCAL_SHOP`
- `BR_LOCAL_SHOP`
- `FR_LOCAL_SHOP`
- `EU_LOCAL_SHOP`
- `EU_CROSS_BORDER_SHOP`

Vietnam-specific notes:

- `VN_CROSS_BORDER_SHOP` now opens `https://seller.tiktokshopglobalselling.com/account/login?`
- `vn.yaml` defaults to `VN_LOCAL_SHOP`

Indonesia-specific notes:

- `id.yaml` defaults to `ID_LOCAL_SHOP`
- `ID_LOCAL_SHOP` opens `https://seller-id.tokopedia.com/account/login?redirect_url=https%3A%2F%2Fseller-id.tokopedia.com%2Fhomepage`
- `ID_LOCAL_SHOP` is currently blocked at login, so the `ID` outreach capture flow is documented but not verified end-to-end yet
- After login, the collector jumps to `https://affiliate.tiktok.com/connection/creator?shop_region=ID` and captures outreach filter metadata with the dedicated `scripts/outreach_filter_id.py`

Brazil-specific notes:

- `br.yaml` defaults to `BR_LOCAL_SHOP`
- `BR_LOCAL_SHOP` opens `https://seller-br.tiktok.com/account/login?lng=en&shop_region=VN&register_referrer=https%3A%2F%2Fseller-br.tiktok.com%2F&redirect_url=https%3A%2F%2Fseller-vn.tiktok.com%2Fhomepage%3Flng%3Den%26shop_region%3DVN`
- `BR_LOCAL_SHOP` is currently blocked at login, so the `BR` outreach capture flow is documented but not verified end-to-end yet
- After login, the collector jumps to `https://affiliate.tiktok.com/connection/creator?shop_region=BR` and captures outreach filter metadata with the dedicated `scripts/outreach_filter_br.py`

France-specific notes:

- `fr.yaml` defaults to `FR_LOCAL_SHOP`
- `FR_LOCAL_SHOP` opens `https://seller-fr-accounts.tiktok.com/account/login?redirect_url=https%3A%2F%2Faffiliate.tiktok.com%2Fconnection%2Fcreator%3Fshop_region%3DFR&lng=en`
- `FR_LOCAL_SHOP` is currently configured for manual login only because account credentials have not been added yet
- After login, the collector jumps to `https://affiliate.tiktok.com/connection/creator?shop_region=FR` and captures outreach filter metadata with the dedicated `scripts/outreach_filter_fr.py`

## Notes

- The current snapshot logic uses one shared selector set for affiliate outreach pages with the same layout. `MX`, `VN`, `ID`, `BR`, and `FR` each have their own app-local script entry so later region-specific behavior can diverge without mixing logic into one file.
- The `ref/` tree is treated as read-only reference material. Runtime outputs and new app files must stay under `apps/portal_tiktok_shop_collection/` or other non-`ref` paths inside the repo.
- The JSON output is meant to be reusable by future client-side DSL execution, so filter changes can be handled by updating captured metadata instead of changing frontend code.
- Europe accounts still need real entry/home URLs before they can be used.
