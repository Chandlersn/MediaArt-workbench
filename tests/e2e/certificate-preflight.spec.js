import { test, expect } from '@playwright/test'
import { STORAGE_KEYS } from '../../src/utils/auth-constants.js'

const SESSION = 'browser-preflight-session'
const NUMBER = 'PREFLIGHT-001'
const TEMPLATE = 'browser-preflight-template'

async function setupCertificates(request) {
  const login = await request.post('/api/auth/login', {
    data: { username: 'browser-admin', password: 'Browser-test-only-2026!' },
  })
  expect(login.ok()).toBeTruthy()
  const auth = await login.json()
  const headers = { Authorization: `Bearer ${auth.access_token}` }
  const snapshot = await (await request.get('/api/data/load', { headers })).json()
  const background = await request.post('/api/print/background', {
    headers,
    multipart: { file: {
      name: 'preflight.png', mimeType: 'image/png',
      buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAADklEQVR4nGP4DwUMMAYAj4IP8TylVlEAAAAASUVORK5CYII=', 'base64'),
    } },
  })
  expect(background.ok()).toBeTruthy()
  const { background: imagePath } = await background.json()
  const name = { column: 'playerName', label: '选手姓名', x: 50, y: 30, fontSize: 18 }
  const work = { column: 'work_name', label: '作品名称', x: 50, y: 50, fontSize: 18 }
  const template = {
    id: TEMPLATE, name: '证书检查验收模板', docType: 'certificate',
    pageSize: 'A4_L', background: imagePath, pageWidth: 2, pageHeight: 2,
    fields: [name, work],
  }
  const sections = {
    certificates: [
      { certNumber: NUMBER, sessionId: SESSION, playerName: '检查选手', workName: '', certRound: '省级展演' },
      { certNumber: 'PREFLIGHT-002', sessionId: SESSION, playerName: '未选中的选手', workName: '（待补）', certRound: '省级展演' },
      { certNumber: NUMBER, sessionId: 'browser-other-session', playerName: '另一批同号选手', workName: '另一批作品', certRound: '省级展演' },
    ],
    certSettings: { activeSessionId: SESSION, sessionMeta: {
      [SESSION]: { name: '打印检查验收', createdAt: '2026-10-05' },
      'browser-other-session': { name: '另一批次', createdAt: '2026-10-04' },
    } },
    printTemplates: [template,
      { ...template, id: `${TEMPLATE}-name`, name: '仅打印姓名', fields: [name] },
      { ...template, id: `${TEMPLATE}-invalid`, name: '字段已失效', fields: [{ ...name, column: 'noSuchCertificateField', label: '已删除字段' }] },
    ],
  }
  const saved = await request.post('/api/data/save', {
    headers,
    data: { ...sections, _snapshot: true,
      _revisions: Object.fromEntries(Object.keys(sections).map(key => [key, snapshot.data._revisions[key]])),
    },
  })
  expect(saved.status()).toBe(200)
  return { auth, headers }
}

async function selectTemplate(page, name) {
  const checked = page.waitForResponse(response => response.url().endsWith('/api/print/validate'))
  await page.locator('.print-modal .custom-select-trigger').click()
  await page.locator('.custom-select-option').filter({ hasText: name }).click()
  expect((await checked).status()).toBe(200)
}

async function openCertificates(page, context, auth) {
  await context.addInitScript(({ auth, keys, session }) => {
    localStorage.setItem(keys.ACCESS_TOKEN, auth.access_token)
    localStorage.setItem(keys.REFRESH_TOKEN, auth.refresh_token)
    localStorage.setItem(keys.USER_INFO, JSON.stringify(auth.user))
    localStorage.setItem(keys.TOKEN_EXPIRES, String(Date.now() + auth.expires_in * 1000))
    localStorage.setItem('workbench_onboarding_done', '1')
    sessionStorage.setItem('workbench_certificate_session', session)
    window.print = () => {}
  }, { auth, keys: STORAGE_KEYS, session: SESSION })
  await page.goto('/#/certificates')
}

test('证书检查、定向补录、自动复检与打印保持同一范围', async ({ page, context, request }) => {
  const { auth, headers } = await setupCertificates(request)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await openCertificates(page, context, auth)
  const targetRow = page.locator('.cert-table tbody tr').filter({ hasText: '检查选手' })
  await targetRow.locator('input[type=checkbox]').check()
  // Completing this field removes the row from this filter; the print range must survive.
  await page.getByRole('button', { name: '仅缺作品名', exact: true }).click()
  const checked = page.waitForResponse(response => response.url().endsWith('/api/print/validate'))
  await page.getByRole('button', { name: /^批量打印/ }).click()
  expect((await checked).status()).toBe(200)
  const modal = page.locator('.print-modal')
  const issues = modal.locator('.print-issue')
  await expect(issues).toHaveCount(1)
  await expect(issues).toContainText('作品名称')
  await expect(issues).toContainText('检查选手')
  await expect(modal).not.toContainText('未选中的选手')

  await selectTemplate(page, '仅打印姓名')
  await expect(issues).toHaveCount(0)
  await selectTemplate(page, '字段已失效')
  await expect(issues).toContainText('已删除字段')
  await expect(modal.getByRole('button', { name: '生成并打印', exact: true })).toBeDisabled()
  await selectTemplate(page, '证书检查验收模板')
  await expect(issues).toHaveCount(1)

  await issues.getByRole('button', { name: '去填写', exact: true }).click()
  const editor = page.locator('.drawer-mask > .drawer')
  const workName = editor.locator('.drawer-row').filter({ has: page.locator('.drawer-label', { hasText: '作品名称' }) }).locator('input')
  await expect(workName).toBeFocused()
  await workName.fill('尚未保存的修改')
  await editor.getByRole('button', { name: '收起', exact: true }).click()
  await expect(editor).toHaveCount(0)
  await expect(issues).toHaveCount(1)

  // A failed save must retain the editor and must not authorize printing.
  await issues.getByRole('button', { name: '去填写', exact: true }).click()
  await workName.fill('保存失败时保留输入')
  await page.route('**/api/data/save', route => route.fulfill({
    status: 500, contentType: 'application/json',
    body: JSON.stringify({ success: false, message: '验收模拟保存失败' }),
  }), { times: 1 })
  const failedSave = page.waitForResponse(response => response.url().endsWith('/api/data/save'))
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  expect((await failedSave).status()).toBe(500)
  await expect(workName).toHaveValue('保存失败时保留输入')
  await expect(editor.getByRole('button', { name: '保存', exact: true })).toBeEnabled()
  await expect(modal).toHaveCount(0)
  const afterFailure = await (await request.get('/api/data/load', { headers })).json()
  expect(afterFailure.data.certificates.find(certificate => certificate.certNumber === NUMBER && certificate.sessionId === SESSION).workName).toBe('')
  await editor.getByRole('button', { name: '收起', exact: true }).click()
  await expect(issues).toHaveCount(1)

  const fillAndRecheck = async value => {
    await issues.getByRole('button', { name: '去填写', exact: true }).click()
    await expect(workName).toBeFocused()
    await workName.fill(value)
    const saved = page.waitForResponse(response => response.url().endsWith('/api/data/save'))
    const rechecked = page.waitForResponse(response => response.url().endsWith('/api/print/validate'))
    await editor.getByRole('button', { name: '保存', exact: true }).click()
    expect((await saved).status()).toBe(200)
    expect((await rechecked).status()).toBe(200)
    await expect(editor).toHaveCount(0)
  }
  await fillAndRecheck('（待补）')
  await expect(issues).toContainText('占位')
  await fillAndRecheck('春日序曲')
  await expect(issues).toHaveCount(0)
  await expect(modal).toContainText('已选 1 份')

  const snapshot = await (await request.get('/api/data/load', { headers })).json()
  const sameNumber = snapshot.data.certificates.filter(certificate => certificate.certNumber === NUMBER)
  expect(sameNumber.find(certificate => certificate.sessionId === SESSION).workName).toBe('春日序曲')
  expect(sameNumber.find(certificate => certificate.sessionId !== SESSION).workName).toBe('另一批作品')

  const generated = page.waitForResponse(response => response.url().endsWith('/api/print/generate'))
  const archived = page.waitForResponse(response => response.url().endsWith('/api/print/archive'))
  const popup = page.waitForEvent('popup')
  await modal.getByRole('button', { name: '生成并打印', exact: true }).click()
  const response = await generated
  expect(response.status()).toBe(200)
  expect(response.request().postDataJSON().certNumbers).toEqual([{ certNumber: NUMBER, sessionId: SESSION }])
  expect(response.request().postDataJSON().validationToken).toBeTruthy()
  const preview = await popup
  await expect(preview.locator('body')).toContainText('春日序曲')
  await expect(preview.locator('body')).not.toContainText('另一批同号选手')
  expect((await archived).request().postDataJSON().refIds).toEqual([{ certNumber: NUMBER, sessionId: SESSION }])
  await preview.close()
  await expect(modal).toHaveCount(0)
  expect(errors).toEqual([])
})

test('表格连续补录保留失败输入，筛选行消失后仍跳到下一份', async ({ page, context, request }) => {
  const { auth, headers } = await setupCertificates(request)
  const snapshot = await (await request.get('/api/data/load', { headers })).json()
  const rows = snapshot.data.certificates.map(row => row.sessionId === SESSION ? { ...row, workName: '', missingWorkName: 1 } : row)
  expect((await request.post('/api/data/save', { headers, data: { certificates: rows, _snapshot: true,
    _revisions: { certificates: snapshot.data._revisions.certificates } } })).ok()).toBeTruthy()
  await openCertificates(page, context, auth)
  await expect(page.locator('.session-label')).toHaveText('证书批次')
  const actions = page.locator('.certificate-actions')
  await expect(actions.getByRole('button', { name: '编号规则', exact: true })).not.toBeVisible()
  await actions.locator('summary').filter({ hasText: '更多' }).click()
  await actions.getByRole('button', { name: '编号规则', exact: true }).click()
  await expect(page.getByText('证书编号规则（可复用模板）', { exact: true })).toBeVisible()
  await actions.locator('summary').filter({ hasText: '导出台账' }).click()
  await expect(actions.getByRole('button', { name: /当前整个批次/ })).toContainText('2 份')
  await page.getByRole('heading', { name: '证书管理', exact: true }).click()
  await expect(actions.locator('details[open]')).toHaveCount(0)

  await page.getByRole('button', { name: '填写检查选手的指导老师', exact: true }).click()
  const teacher = page.getByRole('textbox', { name: '检查选手的指导老师', exact: true })
  await expect(teacher).toBeFocused()
  await teacher.fill('取消的老师')
  await teacher.press('Escape')
  await expect(teacher).toHaveCount(0)
  await page.getByRole('button', { name: '仅缺作品名', exact: true }).click()
  await page.getByRole('button', { name: '填写检查选手的作品名称', exact: true }).click()
  const work = page.getByRole('textbox', { name: '检查选手的作品名称', exact: true })
  await expect(work).toBeFocused()
  await work.fill('第一份作品')
  await page.route('**/api/data/save', route => route.fulfill({ status: 500, contentType: 'application/json',
    body: JSON.stringify({ success: false, message: '验收模拟写入失败' }) }), { times: 1 })
  await work.press('Enter')
  await expect(page.locator('.quick-error')).toContainText('验收模拟写入失败')
  await expect(work).toHaveValue('第一份作品')
  await work.press('Enter')
  const next = page.getByRole('textbox', { name: '未选中的选手的作品名称', exact: true })
  await expect(next).toBeFocused()
  await expect(work).toHaveCount(0)
  await next.fill('第二份作品')
  await next.press('Enter')
  await expect(page.locator('.quick-input')).toHaveCount(0)
  await expect(page.getByText('当前筛选下暂无证书，可调整筛选条件继续查看。', { exact: true })).toBeVisible()
  const after = await (await request.get('/api/data/load', { headers })).json()
  expect(after.data.certificates.find(row => row.certNumber === NUMBER && row.sessionId === SESSION).workName).toBe('第一份作品')
  expect(after.data.certificates.find(row => row.certNumber === NUMBER && row.sessionId !== SESSION).workName).toBe('另一批作品')
  expect(after.data.certificates.find(row => row.certNumber === NUMBER && row.sessionId === SESSION).instructor || '').toBe('')

  await page.getByRole('button', { name: '仅缺作品名', exact: true }).click()
  await actions.locator('summary').filter({ hasText: '更多' }).click()
  await actions.getByRole('button', { name: '打印记录', exact: true }).click()
  await expect(page).toHaveURL(/#\/print$/)
})

test('内嵌预览逐份切换和缩放，预览失败可重试且不记打印记录', async ({ page, context, request }, testInfo) => {
  const { auth, headers } = await setupCertificates(request)
  const logsBefore = await (await request.get('/api/print/logs', { headers })).json()
  await openCertificates(page, context, auth)
  await page.locator('.cert-table thead input[type=checkbox]').check()
  await page.getByRole('button', { name: /^批量打印/ }).click()
  const modal = page.locator('.print-modal')
  const frame = modal.frameLocator('iframe[title="证书打印效果"]')
  await expect(frame.locator('.pf').first()).toHaveText('检查选手')
  await expect(modal.locator('.preview-caption')).toContainText('297 × 210 mm')
  await expect(modal.locator('.preview-pagination')).toContainText('第 1 / 2 份')
  await modal.getByRole('button', { name: '下一份', exact: true }).click()
  await expect(frame.locator('.pf').first()).toHaveText('未选中的选手')
  await expect(frame.locator('body')).not.toContainText('另一批同号选手')
  await modal.getByLabel('预览缩放', { exact: true }).selectOption('1')
  expect(await modal.locator('iframe').evaluate(element => element.style.transform)).toBe('scale(1)')
  await modal.getByLabel('预览缩放', { exact: true }).selectOption('fit')

  await page.route('**/api/print/preview', route => route.fulfill({ status: 500, contentType: 'application/json',
    body: JSON.stringify({ success: false, message: '验收模拟预览失败' }) }), { times: 1 })
  await modal.getByRole('button', { name: '上一份', exact: true }).click()
  await expect(modal.getByRole('alert')).toContainText('验收模拟预览失败')
  await expect(modal.getByRole('button', { name: '仍要生成并打印', exact: true })).toBeDisabled()
  await modal.getByRole('button', { name: '重新检查并预览', exact: true }).click()
  await expect(frame.locator('.pf').first()).toHaveText('检查选手')
  await expect(modal.getByRole('button', { name: '仍要生成并打印', exact: true })).toBeEnabled()
  await testInfo.attach('证书打印窗口', { body: await page.screenshot(), contentType: 'image/png' })

  // Another client changed a certificate after we viewed it. The next click
  // must show the refreshed preview, without creating a print or archive yet.
  const snapshot = await (await request.get('/api/data/load', { headers })).json()
  const updated = snapshot.data.certificates.map(row => row.certNumber === NUMBER && row.sessionId === SESSION ? { ...row, workName: '预览后更新的作品' } : row)
  expect((await request.post('/api/data/save', { headers, data: { certificates: updated, _snapshot: true,
    _revisions: { certificates: snapshot.data._revisions.certificates } } })).ok()).toBeTruthy()
  const generated = []
  page.on('request', request => { if (request.url().endsWith('/api/print/generate')) generated.push(request) })
  await modal.getByRole('button', { name: '仍要生成并打印', exact: true }).click()
  await expect(frame.locator('body')).toContainText('预览后更新的作品')
  await expect(modal).toBeVisible()
  expect(generated).toEqual([])
  const logsAfter = await (await request.get('/api/print/logs', { headers })).json()
  expect(logsAfter.logs).toEqual(logsBefore.logs)
})
