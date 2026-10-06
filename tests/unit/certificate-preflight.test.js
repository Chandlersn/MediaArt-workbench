import fs from 'node:fs'
import assert from 'node:assert/strict'
import { ref, computed, watch, nextTick } from 'vue'
import { useCertificatePrintPreflight } from '../../src/composables/useCertificatePrintPreflight.js'
import { printReferenceKey } from '../../src/utils/printReferences.js'

const read = path => fs.readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8')
const clone = value => JSON.parse(JSON.stringify(value))
const reference = record => ({ certNumber: record.certNumber, sessionId: record.sessionId || '' })
const certKey = record => printReferenceKey(reference(record))
const gate = () => {
  let resolve, reject
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}
const checked = (issues = [], token = 'token') => ({ success: true, itemCount: 1,
  issueCount: issues.length, issues, validationToken: token, canGenerate: !issues.some(issue => issue.severity === 'error') })

function fixture({ canEdit = true } = {}) {
  const rows = ref([
    { certNumber: 'SAME', sessionId: 'first', playerName: 'First', workName: 'First work' },
    { certNumber: 'SAME', sessionId: 'second', playerName: 'Second', workName: '' }
  ])
  const selection = ref([rows.value[1]])
  const calls = { checked: [], generated: [], archived: [], opened: [], errors: [], warnings: [], saves: [], focused: [] }
  const io = { validate: null, generate: null, save: null }
  const templates = [
    { id: 'work', name: 'Work template', fields: [{ column: 'work_name' }] },
    { id: 'name', name: 'Name template', fields: [{ column: 'playerName' }] },
    { id: 'invalid', name: 'Invalid', fields: [{ column: 'deleted' }] }
  ]
  const validate = payload => {
    const issues = []
    if (payload.templateId === 'invalid') issues.push({ kind: 'missing-field', severity: 'error', column: 'deleted', label: 'Invalid field', reference: null, message: 'Field missing' })
    for (const selected of payload.certNumbers) {
      const row = rows.value.find(item => certKey(item) === certKey(selected))
      if (!row) throw new Error('Certificate no longer exists')
      if (payload.templateId === 'work' && (!row.workName || row.workName === '（待补）')) {
        issues.push({ kind: row.workName ? 'placeholder' : 'empty', severity: 'warning', column: 'workName',
          label: '作品名称', reference: reference(row), playerName: row.playerName, value: row.workName,
          message: row.workName ? '疑似占位' : '未填写' })
      }
    }
    return checked(issues, `token-${calls.checked.length}`)
  }
  const env = {
    ref, computed, watch, nextTick, useCertificatePrintPreflight, certKey,
    selectedList: selection, selectedKeys: ref(new Set()), certificates: rows,
    saving: ref(false), canEditCertificates: ref(canEdit),
    userStore: { loadPermissions: async () => {} }, router: { push() {} },
    dataService: { load: async () => {}, getData: () => templates },
    loadPrintIndex: async () => {},
    validatePrint: async payload => {
      calls.checked.push(clone(payload))
      return io.validate ? io.validate(payload) : validate(payload)
    },
    generatePrint: async payload => {
      calls.generated.push(clone(payload))
      if (io.generate) return io.generate(payload)
      return { success: true, html: 'PRINT', itemCount: payload.certNumbers.length }
    },
    archivePrint: async payload => { calls.archived.push(clone(payload)); return { success: true } },
    openHtmlWindow: html => calls.opened.push(html),
    warning: message => calls.warnings.push(message), toastError: message => calls.errors.push(message), success() {},
    console: { warn() {} },
    certStore: { updateCert: async (number, patch, sessionId) => {
      calls.saves.push({ number, patch: clone(patch), sessionId })
      if (io.save) return io.save(number, patch, sessionId)
      const index = rows.value.findIndex(item => item.certNumber === number && item.sessionId === sessionId)
      if (index === -1) return null
      rows.value[index] = { ...rows.value[index], ...patch }
      return rows.value[index]
    } }
  }
  const source = read('src/views/CertificatesView.vue')
  const print = source.slice(source.indexOf('const showPrint ='), source.indexOf('const removeCert ='))
  const edit = source.slice(source.indexOf('const editing ='), source.indexOf('const renderCharts ='))
  const view = new Function(...Object.keys(env), `${print}\n${edit}\nreturn {
    openPrint,runPrint,closePrint,checkPrint,fillPrintIssue,closeEdit,saveEdit,editing,editFromPrint,editDrawer,
    showPrint,printing,printReferences,printTplId,printCheck,printCheckError,printReady,checkingPrint,printAttemptError,printPreviewToken
  };`)(...Object.values(env))
  view.editDrawer.value = { querySelector: selector => ({
    matches: () => true, focus: () => calls.focused.push(selector), scrollIntoView() {}
  }) }
  return { ...view, rows, selection, calls, io, saving: env.saving }
}

describe('Certificate print check and correction', () => {
  it('opens a check only for frozen selected identities and rechecks changed templates', async () => {
    const view = fixture()
    await view.openPrint()
    assert.deepEqual(view.calls.checked[0].certNumbers, [{ certNumber: 'SAME', sessionId: 'second' }])
    assert.equal(view.printCheck.value.issues[0].playerName, 'Second')
    view.selection.value = []
    view.printTplId.value = 'name'
    await nextTick()
    await Promise.resolve()
    assert.equal(view.printCheck.value.issueCount, 0)
    view.printTplId.value = 'invalid'
    await nextTick()
    await Promise.resolve()
    assert.equal(view.printReady.value, false)
    await view.runPrint()
    assert.equal(view.calls.generated.length, 0)
    assert.deepEqual(view.printReferences.value, [{ certNumber: 'SAME', sessionId: 'second' }])
  })

  it('corrects the referenced session and keeps its scope when it leaves a missing-field filter', async () => {
    const view = fixture()
    await view.openPrint()
    await view.fillPrintIssue(view.printCheck.value.issues[0])
    assert.equal(view.editing.value.sessionId, 'second')
    assert.deepEqual(view.calls.focused, ['[data-cert-field="workName"]'])
    view.editing.value.workName = '（待补）'
    await view.saveEdit()
    assert.equal(view.showPrint.value, true)
    assert.equal(view.printCheck.value.issues[0].kind, 'placeholder')
    await view.fillPrintIssue(view.printCheck.value.issues[0])
    view.editing.value.workName = 'Complete work'
    view.selection.value = []
    await view.saveEdit()
    assert.equal(view.printCheck.value.issueCount, 0)
    assert.equal(view.rows.value[0].workName, 'First work')
    await view.runPrint()
    assert.deepEqual(view.calls.generated[0].certNumbers, [{ certNumber: 'SAME', sessionId: 'second' }])
    assert.deepEqual(view.calls.archived[0].refIds, view.calls.generated[0].certNumbers)
    assert.equal(view.calls.generated[0].validationToken, `token-${view.calls.checked.length}`)
    assert.deepEqual(view.calls.errors, [])
  })

  it('canceling edits discards draft values and returns to the original checked range', async () => {
    const view = fixture()
    await view.openPrint()
    await view.fillPrintIssue(view.printCheck.value.issues[0])
    view.editing.value.workName = 'UNSAVED'
    view.selection.value = [view.rows.value[0]]
    await view.closeEdit()
    assert.equal(view.editing.value, null)
    assert.equal(view.showPrint.value, true)
    assert.equal(view.printCheck.value.issues[0].value, '')
    assert.equal(view.calls.saves.length, 0)
    assert.equal(view.printReferences.value[0].sessionId, 'second')
  })

  it('failed or deleted-record saves retain the draft and block closing during an in-flight save', async () => {
    const view = fixture()
    await view.openPrint()
    await view.fillPrintIssue(view.printCheck.value.issues[0])
    view.editing.value.workName = 'KEEP DRAFT'
    const pending = gate()
    view.io.save = () => pending.promise
    const saving = view.saveEdit()
    await view.closeEdit()
    assert.equal(view.saving.value, true)
    assert.equal(view.editing.value.workName, 'KEEP DRAFT')
    pending.reject(new Error('Version conflict'))
    await saving
    assert.equal(view.saving.value, false)
    assert.equal(view.editFromPrint.value, true)
    assert.equal(view.showPrint.value, false)
    assert.equal(view.editing.value.workName, 'KEEP DRAFT')
    view.io.save = async () => null
    await view.saveEdit()
    assert.equal(view.editing.value.workName, 'KEEP DRAFT')
    assert.match(view.calls.errors.at(-1), /未保存/)
  })

  it('viewers can inspect warnings but cannot open or save correction drafts', async () => {
    const view = fixture({ canEdit: false })
    await view.openPrint()
    assert.equal(view.printCheck.value.issueCount, 1)
    await view.fillPrintIssue(view.printCheck.value.issues[0])
    assert.equal(view.editing.value, null)
    await view.saveEdit()
    assert.equal(view.calls.saves.length, 0)
  })

  it('allows explicitly acknowledged warnings but requires a new click for newly found warnings', async () => {
    const view = fixture()
    view.rows.value[1].workName = 'Complete'
    await view.openPrint()
    view.rows.value[1].workName = ''
    await view.runPrint()
    assert.equal(view.calls.generated.length, 0)
    assert.equal(view.printCheck.value.issueCount, 1)
    await view.runPrint()
    assert.equal(view.calls.generated.length, 1)
  })

  it('a failed check cannot authorize generation and retry re-enables the window', async () => {
    const view = fixture()
    view.io.validate = async () => { throw new Error('Check unavailable') }
    await view.openPrint()
    assert.match(view.printCheckError.value, /unavailable/)
    assert.equal(view.printReady.value, false)
    await view.runPrint()
    assert.equal(view.calls.generated.length, 0)
    view.io.validate = null
    await view.checkPrint()
    assert.equal(view.printReady.value, true)
  })

  it('changes after viewing a preview require viewing the new result before generation', async () => {
    const view = fixture()
    view.rows.value[1].workName = 'Complete'
    view.io.validate = async () => checked([], 'previewed-token')
    await view.openPrint()
    view.printPreviewToken.value = 'previewed-token'
    view.io.validate = async () => checked([], 'changed-token')
    await view.runPrint()
    assert.equal(view.calls.generated.length, 0)
    assert.equal(view.showPrint.value, true)
    assert.match(view.calls.warnings.at(-1), /新的预览/)
    view.printPreviewToken.value = 'changed-token'
    await view.runPrint()
    assert.equal(view.calls.generated.length, 1)
  })

  it('409 retains the window and identities, rechecks and never opens or archives stale output', async () => {
    const view = fixture()
    await view.openPrint()
    view.io.generate = async () => { throw Object.assign(new Error('Changed; recheck required'), { status: 409 }) }
    await view.runPrint()
    assert.equal(view.showPrint.value, true)
    assert.equal(view.calls.checked.length, 3)
    assert.deepEqual(view.calls.opened, [])
    assert.deepEqual(view.calls.archived, [])
    assert.match(view.printAttemptError.value, /Changed/)
    view.io.generate = null
    await view.runPrint()
    assert.equal(view.calls.archived.length, 1)
    assert.equal(view.calls.archived[0].refIds[0].sessionId, 'second')
  })

  it('a late check cannot replace a newer template or revive a closed print attempt', async () => {
    const requests = []
    const state = useCertificatePrintPreflight(() => { const request = gate(); requests.push(request); return request.promise })
    state.begin([{ certNumber: 'SAME', sessionId: 'first' }])
    const old = state.check('old')
    const current = state.check('current')
    requests[1].resolve(checked([], 'current-token'))
    await current
    requests[0].resolve(checked([], 'old-token'))
    await old
    assert.equal(state.result.value.validationToken, 'current-token')
    const closed = state.check('closed')
    state.invalidate()
    requests[2].resolve(checked([], 'closed-token'))
    await closed
    assert.equal(state.result.value, null)
    assert.equal(state.checking.value, false)
  })

  it('the real print service preserves an HTTP 409 for the UI', async () => {
    const script = read('src/services/print.js').replace(/^import .*$/mg, '').replace(/^export /mg, '')
    const service = new Function('get', 'post', 'fetchWithAuth', `${script}\nreturn {generatePrint,validatePrint};`)(
      async () => {}, async (path, payload) => ({ path, payload }),
      async () => ({ ok: false, status: 409, json: async () => ({ message: '证书或模板已变更，请重新检查后再生成' }) }))
    await assert.rejects(service.generatePrint({ validationToken: 'old' }), error => error.status === 409 && /变更/.test(error.message))
    assert.equal((await service.validatePrint({ templateId: 't' })).path, '/api/print/validate')
  })
})
