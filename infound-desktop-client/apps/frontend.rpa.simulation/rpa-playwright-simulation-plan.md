# RPA Playwright Simulation Plan

## Goal

Split session startup from task execution.

1. `登录店铺`: only prepares login state
2. `启动RPA模拟`: only starts a Playwright session and keeps it idle
3. Specific task commands then run robots inside that existing Playwright session

This implementation stays inside `apps/frontend.rpa.simulation`.

## Scope

Current Playwright session covers 4 robot commands:

1. Outreach
2. Sample Management
3. Seller Chatbot
4. Creator Detail

## Architecture

### UI

File: `src/renderer/src/App.vue`

- Keep `登录店铺` button unchanged.
- Use `启动RPA模拟` button to start the Playwright session.
- Do not auto-run any robot when the session starts.

### IPC

Files:

- `src/common/types/ipc-type.ts`
- `src/common/types/rpa-simulation.ts`
- `src/main/modules/ipc/rpa-controller.ts`

Current model:

- `RPA_EXECUTE_SIMULATION`: start Playwright session only
- `RPA_SELLER_OUT_REACH`: dispatch outreach task to current Playwright session
- `RPA_SAMPLE_MANAGEMENT`: dispatch sample-management task to current Playwright session
- `RPA_SELLER_CHATBOT`: dispatch chatbot task to current Playwright session
- `RPA_SELLER_CREATOR_DETAIL`: dispatch creator-detail task to current Playwright session

Session payload model:

- `region`
- `headless`
- `storageStatePath`

### Execution backend

Directory: `src/main/modules/rpa/playwright-simulation/`

Files:

1. `playwright-simulation-service.ts`
   - Owns a persistent Playwright browser/context/page session.
   - Starts and keeps the session idle on affiliate homepage if storage state exists.
   - Falls back to seller login page and waits for manual login if storage state is missing.
   - Queues robot tasks onto the same session.
2. `playwright-browser-target.ts`
   - Implements current `BrowserActionTarget` on Playwright `Page`.
3. `playwright-response-capture.ts`
   - Captures JSON responses from Playwright network events.
4. `sample-management-playwright.ts`
   - Keeps sample-management as an independent business runner.
5. `shared.ts`
   - Small shared helpers.

## DSL strategy

Do not create a second Playwright-only DSL.

Use the existing BrowserTask DSL and reuse current robot task builders:

- Outreach support: `src/main/modules/rpa/outreach/support.ts`
- Chatbot support: `src/main/modules/rpa/chatbot/support.ts`
- Creator detail support: `src/main/modules/rpa/creator-detail/support.ts`

Only the execution backend is Playwright.

## Page navigation

Task execution pages stay aligned with the previous Electron robots:

1. Outreach:
   - `https://affiliate.tiktok.com/connection/creator?shop_region=<region>`
2. Sample Management:
   - `https://affiliate.tiktok.com/product/sample-request?shop_region=<region>`
3. Chatbot:
   - `https://affiliate.tiktok.com/seller/im?creator_id=<creator_id>&shop_region=<region>`
4. Creator Detail:
   - `https://affiliate.tiktok.com/connection/creator/detail?cid=<creator_id>&shop_region=<region>`

The only startup page difference is session bootstrap:

- session idle page:
  - `https://affiliate.tiktok.com/platform/homepage?shop_region=<region>`

## Login-state assumption

This implementation first tries to use a prepared Playwright storage state file.

Default path:

- `data/playwright/storage-state.json`

If the file does not exist, session startup no longer aborts.
It opens the seller login page and waits for manual operation.
If the requested mode is headless in this case, it is forced back to headed mode.

## Current implementation status

Completed in this phase:

1. `启动RPA模拟` now starts a persistent Playwright session only.
2. Session startup is headed by default, configurable to headless.
3. Session startup no longer auto-runs the 4 robots.
4. Individual robot commands now dispatch onto the Playwright session.
5. Old Electron robot execution path has been removed from the simulation main chain.
6. CLI commands now follow the same start-session-then-dispatch model.

## Operational model

1. Start app.
2. Start Playwright session.
3. Wait until browser is idle on affiliate homepage, or complete manual login if the browser opened the login page.
4. Send one or more robot commands.
5. Tasks run sequentially on the same Playwright session.
