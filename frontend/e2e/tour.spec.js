// The guided tour and the getting-started checklist (Phase 8 steps 1–2): real data, empty states, keyboard, resume,
// replay, phones (bottom sheet), accessibility, deep links, hide/restore, and neither in the demo.
import AxeBuilder from '@axe-core/playwright'
import { test, expect, checkLayout, newAccount, callApi, seedData, signIn, reopen } from './fixtures'

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
const STEPS = 7

async function freshWithData(page, request) {
  const a = await newAccount(request)
  await callApi(request, a, 'GET', '/auth/me')
  await seedData(request, a)                                            // finishes setup and marks the tour seen
  await callApi(request, a, 'PATCH', '/api/tour', { status: 'active', step: 0 })
  await signIn(page, a)
  return a
}

const tour = (page) => page.getByTestId('tour')
const card = (page) => tour(page).getByRole('dialog')

test('walks through the home page with the user\'s own numbers, by keyboard, and resumes after a reload', async ({ page, request }, testInfo) => {
  const a = await freshWithData(page, request)
  await expect(card(page)).toHaveAccessibleName('Safe to spend today')
  await expect(card(page)).toContainText(/₹[\d,]+ is what you can spend today/)
  await expect(card(page).getByRole('button', { name: 'Next' })).toBeFocused()
  await expect(card(page)).toContainText(`Step 1 of ${STEPS}`)
  const { violations } = await new AxeBuilder({ page }).include('[data-testid="tour"]').withTags(TAGS).analyze()
  expect(violations.map((v) => v.id)).toEqual([])
  await checkLayout(page, testInfo)

  await page.keyboard.press('ArrowRight')
  await expect(card(page)).toHaveAccessibleName('Add anything in one line')
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('ArrowLeft')
  await expect(card(page)).toHaveAccessibleName('Add anything in one line')
  await page.keyboard.press('Tab'); await page.keyboard.press('Tab'); await page.keyboard.press('Tab')
  expect(await page.evaluate(() => Boolean(document.activeElement?.closest('[data-testid="tour"]')))).toBe(true)   // focus stays in the card

  await card(page).getByRole('button', { name: 'Next' }).click()
  await expect(card(page)).toHaveAccessibleName('Questions that fix your numbers')
  await expect.poll(async () => (await callApi(request, a, 'GET', '/api/tour')).step).toBe(2)
  await reopen(page)                                                     // the server kept the place
  await expect(card(page)).toHaveAccessibleName('Questions that fix your numbers')

  for (let i = 3; i < STEPS; i++) {                                     // by key: see "without data" below
    await card(page).getByRole('button', { name: 'Next' }).press('Enter')
    await expect(card(page)).toContainText(`Step ${i + 1} of ${STEPS}`)
  }
  await expect(card(page)).toHaveAccessibleName("That's the tour")
  await card(page).getByRole('button', { name: 'Done' }).click()
  await expect(tour(page)).toHaveCount(0)
  await expect.poll(async () => (await callApi(request, a, 'GET', '/api/tour')).status).toBe('done')
  await reopen(page)
  await expect(page.getByText('Safe to spend today')).toBeVisible()
  await expect(tour(page)).toHaveCount(0)                                // finished: doesn't come back by itself
})

test('"?" replays it from the start, Escape skips, and on phones it is a bottom sheet', async ({ page, request }) => {
  const a = await newAccount(request)
  await callApi(request, a, 'GET', '/auth/me')
  await seedData(request, a)
  await signIn(page, a)
  await expect(page.getByText('Safe to spend today')).toBeVisible()
  await expect(tour(page)).toHaveCount(0)
  await page.getByRole('button', { name: 'Take the tour' }).first().click()
  await expect(card(page)).toHaveAccessibleName('Safe to spend today')
  if (page.viewportSize().width < 640) {
    // against the full-screen overlay it sits in: that is the viewport fixed elements get (Playwright's WebKit on macOS
    // draws classic scrollbars, so window.innerWidth/innerHeight include gutters a phone doesn't have)
    await expect.poll(() => card(page).evaluate((el) => {
      const r = el.getBoundingClientRect(), o = el.parentElement.getBoundingClientRect()
      return Math.abs(r.bottom - o.bottom) <= 1 && Math.abs(r.width - o.width) <= 1 && Math.abs(r.left - o.left) <= 1
    })).toBe(true)
  }
  await expect(card(page).getByRole('button', { name: 'Next' })).toBeFocused()       // the card is ready for keys
  await page.keyboard.press('Escape')
  await expect(tour(page)).toHaveCount(0)
  await expect.poll(async () => (await callApi(request, a, 'GET', '/api/tour')).status).toBe('skipped')
})

test('without data, the steps say what will appear', async ({ page, request }) => {
  const a = await newAccount(request)
  await callApi(request, a, 'GET', '/auth/me')
  await callApi(request, a, 'PATCH', '/api/onboarding', { status: 'skipped' })
  await signIn(page, a)
  await expect(card(page)).toHaveAccessibleName('Safe to spend today')     // starts by itself after setup
  await expect(card(page)).toContainText('Once vaulta.in knows your income or a budget')
  for (let i = 1; i <= 3; i++) {
    // a key press, not a pointer click: the card follows the smooth scroll to the next element, and Firefox's clicks
    // could land beside a card still moving (the pointer click itself is tested once, in the first test)
    await card(page).getByRole('button', { name: 'Next' }).press('Enter')
    await expect(card(page)).toContainText(`Step ${i + 1} of ${STEPS}`)
  }
  await expect(card(page)).toContainText('Import a statement or forward a bank alert')
})

test('the checklist ticks from what was done, links to the next thing, hides and comes back', async ({ page, request }, testInfo) => {
  const a = await newAccount(request)
  await callApi(request, a, 'GET', '/auth/me')
  await seedData(request, a)                                            // an import and a budget
  await signIn(page, a)
  const list = page.getByTestId('getting-started')
  await expect(list).toBeVisible()
  await expect(list.getByText('Import a bank statement (done)')).toBeAttached()
  await expect(list.getByText('Set a monthly budget (done)')).toBeAttached()
  await expect(list.getByRole('progressbar', { name: 'Getting started progress' })).toHaveAttribute('aria-valuenow', /\d+/)
  await checkLayout(page, testInfo)

  await list.getByRole('link', { name: 'Open your review queue' }).click()
  await expect(page).toHaveURL(/\/review$/)
  await expect.poll(async () => (await callApi(request, a, 'GET', '/api/checklist')).items.find((i) => i.id === 'review').done).toBe(true)
  await page.goto('/')
  await expect(page.getByTestId('getting-started').getByText('Open your review queue (done)')).toBeAttached()

  await page.getByTestId('getting-started').getByRole('button', { name: 'Hide this list' }).click()
  await expect(page.getByTestId('getting-started')).toHaveCount(0)
  await page.goto('/settings')
  await page.getByRole('button', { name: 'Show the getting-started list' }).click()
  await expect(page.getByRole('button', { name: 'Show the getting-started list' })).toHaveCount(0)
  await page.goto('/')
  await expect(page.getByTestId('getting-started')).toBeVisible()
})

test('the demo has no tour, no checklist and no tour button', async ({ page }) => {
  await page.goto('/welcome')
  await page.getByRole('button', { name: /look around the demo|try the demo/i }).first().click()
  await expect(page.getByText("You're viewing a demo with sample data.")).toBeVisible()
  await expect(page.getByText('Safe to spend today')).toBeVisible()
  await expect(tour(page)).toHaveCount(0)
  await expect(page.getByTestId('getting-started')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Take the tour' })).toHaveCount(0)
})
