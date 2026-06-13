#!/usr/bin/env node
/**
 * Playwright smoke test against the live skywatch-test dashboard.
 *
 * Prereqs (run in order):
 *   1. mise run install         # SCP + restart HA
 *   2. add Skywatch in HA UI
 *   3. mise run deploy:test-dashboard
 *   4. mise run setup:browser   # installs Playwright + Chromium
 *
 * Then:
 *   mise run verify:browser
 *
 * Env:
 *   HA_HOST   default 10.100.100.200
 *   HA_PORT   default 8123
 *   HA_TOKEN  required — Long-Lived Access Token used to skip the
 *             login page via the auth-cookie injection trick
 *   OUTDIR    default ./.verify-screenshots
 *
 * Reports pass/fail per assertion to stdout. Saves screenshots per
 * viewport into OUTDIR. Exit code non-zero on any failed assertion.
 */
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

const HA_HOST = process.env.HA_HOST || '10.100.100.200';
const HA_PORT = process.env.HA_PORT || '8123';
const HA_TOKEN = process.env.HA_TOKEN;
const OUTDIR = process.env.OUTDIR || './.verify-screenshots';
const BASE = `http://${HA_HOST}:${HA_PORT}`;
const DASHBOARD = '/skywatch-test/skywatch-test';

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet',  width: 1024, height: 1366 },
  { name: 'phone',   width: 414,  height: 896 },
];

const EXPECTED_TEXTS = [
  'Skywatch counts',
  'Sightings today',
  'Sightings this week',
  'Sightings all-time',
  'Overhead transits',
  'Military sightings',
  'Aircraft present',
  'Helicopter overhead',
  'Live map',
];

const FORBIDDEN_TEXTS = [
  'Entity not available',
  'unavailable',
  'unknown',
  'undefined',
];

if (!HA_TOKEN) {
  console.error('HA_TOKEN env var required');
  process.exit(2);
}

mkdirSync(OUTDIR, { recursive: true });

const failures = [];

async function run() {
  const browser = await chromium.launch({ headless: true });

  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
    });
    const page = await ctx.newPage();

    // Suppress noisy console while still collecting errors.
    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    // Inject the HA auth token before navigation — HA reads it from
    // hass['auth'] in IndexedDB. This trick is documented in HA's
    // own front-end test harness.
    await page.addInitScript(([token, host]) => {
      const hassTokens = {
        access_token: token,
        token_type: 'Bearer',
        refresh_token: '',
        expires: Date.now() + 24 * 60 * 60 * 1000,
        expires_in: 1800,
        hassUrl: `http://${host}:8123`,
        clientId: null,
      };
      window.localStorage.setItem('hassTokens', JSON.stringify(hassTokens));
      window.localStorage.setItem('selectedLanguage', '"en"');
    }, [HA_TOKEN, HA_HOST]);

    console.log(`\n==> Viewport ${vp.name} (${vp.width}x${vp.height})`);
    try {
      await page.goto(`${BASE}${DASHBOARD}`, { waitUntil: 'networkidle', timeout: 30_000 });
    } catch (err) {
      failures.push(`${vp.name}: navigation failed: ${err.message}`);
      await ctx.close();
      continue;
    }

    // Allow Lovelace to render past the initial paint.
    await page.waitForTimeout(3000);

    // Playwright's locator() pierces shadow DOM (Lovelace tile cards
    // wrap their text in shadow roots). document.body.innerText does
    // NOT pierce them — would always show 0 hits.
    for (const needle of EXPECTED_TEXTS) {
      const count = await page.getByText(needle).count();
      if (count === 0) {
        failures.push(`${vp.name}: missing expected text "${needle}"`);
      } else {
        console.log(`  + "${needle}" present (${count}×)`);
      }
    }

    const errCount = await page.getByText('Entity not available').count();
    if (errCount > 0) {
      failures.push(`${vp.name}: "Entity not available" found ${errCount}×`);
    }
    const unauthCount = await page.getByText(/401:?\s*Unauthorized/i).count();
    if (unauthCount > 0) {
      failures.push(`${vp.name}: map iframe shows ${unauthCount}× '401 Unauthorized'`);
    }

    // Filter out HA's own CSS warnings (`Custom state pseudo classes`)
    // which are noise about a browser-spec rename and not bugs in our code.
    const realErrors = consoleErrors.filter(
      (line) => !line.includes('Custom state pseudo classes')
    );
    if (realErrors.length) {
      failures.push(`${vp.name}: ${realErrors.length} console error(s):\n    ${realErrors.slice(0, 3).join('\n    ')}`);
    } else {
      console.log(`  + no console errors (filtered ${consoleErrors.length - realErrors.length} CSS warning${consoleErrors.length - realErrors.length === 1 ? '' : 's'})`);
    }

    const png = join(OUTDIR, `skywatch-test-${vp.name}.png`);
    await page.screenshot({ path: png, fullPage: true });
    console.log(`  screenshot → ${png}`);

    await ctx.close();
  }

  await browser.close();

  console.log('\n==> Summary');
  if (failures.length === 0) {
    console.log('  ALL PASSED');
    process.exit(0);
  } else {
    console.log(`  ${failures.length} FAILURE(S):`);
    for (const f of failures) console.log(`    - ${f}`);
    process.exit(1);
  }
}

await run();
