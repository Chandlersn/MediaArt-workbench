import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { STORAGE_KEYS } from '../../src/utils/auth-constants.js'

async function choose(page, container, option) {
  await container.locator('.custom-select-trigger').click()
  await page.locator('.custom-select-option').filter({ hasText: new RegExp(`^${option}$`) }).click()
}

function group(page, name) {
  return page.locator('.form-group').filter({ has: page.locator('label', { hasText: name }) })
}

async function snapshot(page) {
  return page.evaluate(async tokenKey => {
    const response = await fetch('/api/data/load', {
      headers: { Authorization: `Bearer ${localStorage.getItem(tokenKey)}` },
    })
    if (!response.ok) throw new Error(`Data load failed: ${response.status}`)
    return (await response.json()).data
  }, STORAGE_KEYS.ACCESS_TOKEN)
}

async function saveAndWait(page, button) {
  const response = page.waitForResponse(r => r.url().endsWith('/api/data/save') && r.request().method() === 'POST')
  await button.click()
  expect((await response).status()).toBe(200)
}

test('创建项目与选手、收集资料、同步证书、打印归档并恢复备份', async ({ page, context }, testInfo) => {
  const pageErrors = []
  const failedRequests = []
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('response', response => {
    if (response.url().includes('/api/') && response.status() >= 400) {
      failedRequests.push(`${response.status()} ${response.url()}`)
    }
  })
  // Exercise preview windows without sending anything to an actual printer.
  await context.addInitScript(() => { window.print = () => {} })

  let projectId, playerId, certificateNumber, sessionId, backupName

  await test.step('真实登录与首次使用引导', async () => {
    await page.goto('/')
    await page.locator('.user-info').getByRole('button', { name: '登录', exact: true }).click()
    await page.getByPlaceholder('请输入用户名').fill('browser-admin')
    await page.getByPlaceholder('请输入密码', { exact: true }).fill('Browser-test-only-2026!')
    await page.locator('.login-modal').getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.locator('.user-info').getByRole('button', { name: '退出' })).toBeVisible()
    await page.getByRole('button', { name: '开始使用' }).click()
  })

  await test.step('新建项目、机构、选手并验证关联持久化', async () => {
    await page.goto('/#/projects/new')
    await page.getByPlaceholder('请输入项目名称').fill('浏览器验收项目')
    await choose(page, group(page, '项目类型'), '艺术展演')
    await saveAndWait(page, page.getByRole('button', { name: '创建项目', exact: true }))
    await expect(page).toHaveURL(/#\/projects$/)
    projectId = (await snapshot(page)).projects.find(row => row.name === '浏览器验收项目').id

    await page.goto('/#/organizations/new')
    await page.getByPlaceholder('请输入机构名称').fill('浏览器验收机构')
    await saveAndWait(page, page.getByRole('button', { name: '添加机构', exact: true }))
    await expect(page).toHaveURL(/#\/organizations$/)

    await page.goto('/#/players/new')
    await page.getByPlaceholder('请输入姓名', { exact: true }).fill('验收选手')
    await choose(page, group(page, '艺术类别'), '美术')
    await choose(page, group(page, '所属项目'), '浏览器验收项目')
    await choose(page, group(page, '所属机构'), '浏览器验收机构')
    await choose(page, group(page, '当前阶段'), '初赛')
    await saveAndWait(page, page.getByRole('button', { name: '添加选手', exact: true }))
    await expect(page).toHaveURL(/#\/players$/)
    const players = (await snapshot(page)).players
    expect(players).toHaveLength(1)
    playerId = players[0].id
    expect(players[0].projectId).toBe(projectId)
    expect(players[0].orgId).toBeTruthy()
  })

  await test.step('资料按阶段检查，上传、刷新、删除后状态一致', async () => {
    await page.goto(`/#/players/${playerId}`)
    await expect(page.locator('.missing-materials-alert')).toContainText('报名表')
    const upload = page.locator('.material-upload-section')
    const uploadForStage = async (stage, materialType = '报名表') => {
      await choose(page, upload.locator('.custom-select').nth(0), materialType)
      await choose(page, upload.locator('.custom-select').nth(1), stage)
      await upload.locator('input[type=file]').setInputFiles({
        name: '扫描件.pdf', mimeType: 'application/pdf', buffer: Buffer.from(`%PDF-1.4\n${materialType}\n%%EOF`),
      })
      const uploaded = page.waitForResponse(r => r.url().endsWith('/api/upload'))
      await upload.getByRole('button', { name: '上传', exact: true }).click()
      expect((await uploaded).status()).toBe(200)
      await expect(upload.getByRole('button', { name: '上传', exact: true })).toBeDisabled()
    }
    await uploadForStage('省赛')
    await expect(page.locator('.material-item')).toHaveCount(1)
    await expect(page.locator('.missing-materials-alert')).toContainText('报名表')
    await uploadForStage('初赛')
    await expect(page.locator('.missing-materials-alert')).toHaveCount(0)
    await page.reload()
    const currentStage = page.locator('.stage-group').filter({ has: page.locator('.stage-group-name', { hasText: '初赛' }) })
    await expect(currentStage.locator('.material-item')).toHaveCount(1)
    await expect(currentStage.locator('.material-type')).toHaveText('报名表')
    await expect(page.locator('.missing-materials-alert')).toHaveCount(0)
    // Same basename in distinct classification folders must identify the exact file.
    await uploadForStage('初赛', '作品集')
    const portfolio = currentStage.locator('.material-item').filter({ has: page.locator('.material-type', { hasText: '作品集' }) })
    const downloadEvent = page.waitForEvent('download')
    await portfolio.getByRole('button', { name: '下载', exact: true }).click()
    const downloaded = await downloadEvent
    expect((await readFile(await downloaded.path())).toString()).toBe('%PDF-1.4\n作品集\n%%EOF')
    const deleteRow = async row => {
      await row.getByRole('button', { name: '删除', exact: true }).click()
      const deleted = page.waitForResponse(r => r.url().endsWith('/api/delete-player-material'))
      await page.locator('.confirm-dialog').getByRole('button', { name: '确定', exact: true }).click()
      expect((await deleted).status()).toBe(200)
      await expect(row).toHaveCount(0)
    }
    await deleteRow(portfolio)
    await expect(currentStage.locator('.material-type')).toHaveText('报名表')
    await expect(page.locator('.missing-materials-alert')).toHaveCount(0)
    await deleteRow(currentStage.locator('.material-item').filter({ has: page.locator('.material-type', { hasText: '报名表' }) }))
    await expect(page.locator('.missing-materials-alert')).toContainText('报名表')
    await uploadForStage('初赛')
    await expect(page.locator('.missing-materials-alert')).toHaveCount(0)
    await page.goto('/#/players')
    await expect(page.locator('.player-card')).toHaveCount(1)
    await expect(page.locator('.missing-badge')).toHaveCount(0)
  })

  await test.step('重复同步保留同一证书、批次及项目关联', async () => {
    await page.goto('/#/certificates')
    await page.getByRole('button', { name: '从选手同步', exact: true }).click()
    await saveAndWait(page, page.getByRole('button', { name: '开始同步', exact: true }))
    await expect(page.locator('.cert-table tbody tr')).toHaveCount(1)
    const [certificate] = (await snapshot(page)).certificates
    certificateNumber = certificate.certNumber
    sessionId = certificate.sessionId
    expect(certificate.projectId).toBe(projectId)
    await page.getByRole('button', { name: '从选手同步', exact: true }).click()
    await saveAndWait(page, page.getByRole('button', { name: '开始同步', exact: true }))
    await expect(page.locator('.cert-table tbody tr')).toHaveCount(1)
    await expect(page.locator('.session-chip')).toHaveCount(1)
    const [again] = (await snapshot(page)).certificates
    expect(again.certNumber).toBe(certificateNumber)
    expect(again.sessionId).toBe(sessionId)
  })

  await test.step('通过模板编辑器创建可用的打印模板', async () => {
    await page.goto('/#/templates')
    await page.getByRole('button', { name: '新建打印模板' }).click()
    await page.getByPlaceholder('如：2026 省级展演获奖证书').fill('浏览器验收模板')
    const uploaded = page.waitForResponse(r => r.url().endsWith('/api/print/background'))
    await page.locator('input[type=file]').first().setInputFiles({
      name: 'background.png', mimeType: 'image/png',
      buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAADklEQVR4nGP4DwUMMAYAj4IP8TylVlEAAAAASUVORK5CYII=', 'base64'),
    })
    expect((await uploaded).status()).toBe(200)
    await expect.poll(() => page.locator('.tpl-bg').evaluate(img => img.naturalWidth)).toBeGreaterThan(0)
    await page.locator('label.chk').filter({ hasText: '选手姓名' }).getByRole('checkbox').check()
    await saveAndWait(page, page.getByRole('button', { name: '保存模板', exact: true }))
    await expect(page.locator('.tpl-card')).toHaveCount(1)
    await page.reload()
    await expect(page.locator('.tpl-card')).toContainText('浏览器验收模板')
  })

  await test.step('批量生成真实预览、归档并从打印中心回看', async () => {
    await page.goto('/#/certificates')
    await page.locator('.cert-table tbody input[type=checkbox]').check()
    await page.getByRole('button', { name: /^批量打印/ }).click()
    const preview = page.waitForEvent('popup')
    const archived = page.waitForResponse(r => r.url().endsWith('/api/print/archive'))
    await page.getByRole('button', { name: '生成并打印' }).click()
    const popup = await preview
    await expect(popup.locator('body')).toContainText('验收选手')
    expect((await archived).status()).toBe(200)
    await popup.close()
    await page.goto('/#/print')
    await expect(page.locator('.log-table tbody tr')).toHaveCount(1)
    const archivedPreview = page.waitForEvent('popup')
    await page.getByRole('button', { name: '查看', exact: true }).click()
    const document = await archivedPreview
    await expect(document.locator('body')).toContainText('验收选手')
    await document.close()
    await page.getByRole('button', { name: '重打', exact: true }).click()
    const reprintedPreview = page.waitForEvent('popup')
    const reprinted = page.waitForResponse(r => r.url().endsWith('/api/print/generate'))
    const rearchived = page.waitForResponse(r => r.url().endsWith('/api/print/archive'))
    await page.locator('.confirm-dialog').getByRole('button', { name: '重打', exact: true }).click()
    const reprintResponse = await reprinted
    expect(reprintResponse.request().postDataJSON().certNumbers).toEqual([{ certNumber: certificateNumber, sessionId }])
    const reprintDocument = await reprintedPreview
    await expect(reprintDocument.locator('body')).toContainText('验收选手')
    expect((await rearchived).status()).toBe(200)
    await reprintDocument.close()
    await expect(page.locator('.log-table tbody tr')).toHaveCount(2)
  })

  await test.step('真实备份、修改项目、从界面恢复并重新读取业务结果', async () => {
    await page.goto('/#/settings')
    await page.getByRole('button', { name: '备份管理', exact: true }).click()
    const backupResponse = page.waitForResponse(r => r.url().endsWith('/api/data/backup'))
    await page.getByRole('button', { name: '创建备份', exact: true }).click()
    backupName = (await (await backupResponse).json()).backup_name
    expect(backupName).toBeTruthy()
    await page.locator('.modal-content').filter({ has: page.getByRole('heading', { name: '备份管理' }) })
      .getByRole('button', { name: '关闭', exact: true }).click()
    await page.goto(`/#/projects/${projectId}/edit`)
    await expect(page.getByPlaceholder('请输入项目名称')).toHaveValue('浏览器验收项目')
    await page.getByPlaceholder('请输入项目名称').fill('备份后修改的名称')
    await saveAndWait(page, page.getByRole('button', { name: '保存修改', exact: true }))
    expect((await snapshot(page)).projects).toHaveLength(1)
    await page.goto('/#/settings')
    await page.getByRole('button', { name: '备份管理', exact: true }).click()
    await page.locator('.backup-item').getByRole('button', { name: '恢复', exact: true }).click()
    const restored = page.waitForResponse(r => r.url().endsWith('/api/data/restore'))
    const reloaded = page.waitForEvent('load')
    await page.locator('.confirm-dialog').getByRole('button', { name: '确定', exact: true }).click()
    expect((await restored).status()).toBe(200)
    await reloaded
    await expect(page.getByRole('heading', { name: '设置', exact: true })).toBeVisible()
    const data = await snapshot(page)
    expect(data.projects[0].name).toBe('浏览器验收项目')
    expect(data.players[0].id).toBe(playerId)
    expect(data.certificates[0].certNumber).toBe(certificateNumber)
    expect(data.printTemplates[0].name).toBe('浏览器验收模板')
  })

  await test.step('退出登录后首页清空业务展示且不再请求受保护数据', async () => {
    await page.locator('.user-info').getByRole('button', { name: '退出' }).click()
    await expect(page).toHaveURL(/#\/$/)
    await expect(page.getByText('登录后查看项目、选手和待办数据。请点击右上角“登录”。')).toBeVisible()
    await expect(page.locator('.user-info').getByRole('button', { name: '登录', exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByText('登录后查看项目、选手和待办数据。请点击右上角“登录”。')).toBeVisible()
    await expect(page.locator('.login-modal')).toHaveCount(0)
  })

  await testInfo.attach('browser-runtime-checks', {
    body: JSON.stringify({ pageErrors, failedRequests, projectId, playerId, certificateNumber, sessionId, backupName }, null, 2),
    contentType: 'application/json',
  })
  expect(pageErrors).toEqual([])
  expect(failedRequests).toEqual([])
})
