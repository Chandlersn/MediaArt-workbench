import fs from 'node:fs'
import assert from 'node:assert/strict'
import { ref, computed, watch } from 'vue'
import { useCertificatePrintPreflight } from '../../src/composables/useCertificatePrintPreflight.js'
import {
  parsePrintReferences, printReferenceKey, printReferenceNumber, indexPrintReferences
} from '../../src/utils/printReferences.js'

const source = file => fs.readFileSync(new URL(`../../src/views/${file}.vue`, import.meta.url), 'utf8')
const pick = (file, start, end) => {
  const text = source(file)
  const first = text.indexOf(start)
  const last = text.indexOf(end, first)
  assert.ok(first >= 0 && last > first, `Missing view section: ${start}`)
  return text.slice(first, last)
}
const execute = (text, env, exports) => new Function(...Object.keys(env), `${text}\nreturn {${exports}};`)(...Object.values(env))
const clone = value => JSON.parse(JSON.stringify(value))

function printIO() {
  const calls = { generated: [], archived: [], opened: [], errors: [] }
  const env = {
    ref, computed, watch, useCertificatePrintPreflight, confirm: async () => true,
    validatePrint: async payload => ({ success: true, itemCount: payload.certNumbers.length,
      issueCount: 0, issues: [], canGenerate: true, validationToken: 'checked-token' }),
    generatePrint: async payload => {
      calls.generated.push(clone(payload))
      return { success: true, html: '<html>certificate</html>', itemCount: payload.certNumbers.length }
    },
    archivePrint: async payload => { calls.archived.push(clone(payload)); return { success: true } },
    fetchPrintLogs: async () => ({ success: true, logs: [] }),
    openHtmlWindow: html => calls.opened.push(html),
    warning: () => {}, success: () => {}, toastError: error => calls.errors.push(error)
  }
  return { calls, env }
}

describe('Print references retain certificate sessions', () => {
  it('reads new objects and legacy strings without inventing a session', () => {
    const old = 'P0001'
    const current = { certNumber: 'P0001', sessionId: 'second-session' }
    assert.deepEqual(parsePrintReferences(JSON.stringify([old, current])), [old, current])
    assert.deepEqual(parsePrintReferences([null, {}, [], '', { certNumber: 'P0002' }]), [{ certNumber: 'P0002' }])
    assert.deepEqual(parsePrintReferences('broken json'), [])
    assert.deepEqual(parsePrintReferences('{}'), [])
    assert.equal(printReferenceNumber(current), old)
    assert.notEqual(printReferenceKey(old), printReferenceKey(current))
    assert.notEqual(printReferenceKey(old), printReferenceKey({ certNumber: old, sessionId: '' }))
  })

  it('certificate printing archives the same identities sent to generation', async () => {
    const { calls, env } = printIO()
    const references = [
      { certNumber: 'P0001', sessionId: 'first-session' },
      { certNumber: 'P0001', sessionId: 'second-session' }
    ]
    const selection = ref(clone(references))
    const generate = env.generatePrint
    env.generatePrint = async payload => {
      const result = await generate(payload)
      selection.value = [{ certNumber: 'CHANGED', sessionId: 'another' }]
      return result
    }
    Object.assign(env, {
      selectedList: selection, selectedKeys: ref(new Set()), saving: ref(false),
      loadPrintIndex: async () => {},
      dataService: { load: async () => {}, getData: () => [{ id: 'template', name: 'Certificates', fields: [] }] },
      userStore: { loadPermissions: async () => {} }, router: { push() {} }
    })
    const view = execute(pick('CertificatesView', 'const showPrint =', 'const removeCert ='), env, 'openPrint,runPrint')
    await view.openPrint()
    await view.runPrint()
    assert.deepEqual(calls.errors, [])
    assert.deepEqual(calls.generated[0].certNumbers, references)
    assert.equal(calls.generated[0].validationToken, 'checked-token')
    assert.deepEqual(calls.archived[0].refIds, references)
    assert.equal(calls.opened.length, 1)
  })

  for (const references of [
    [{ certNumber: 'P0001', sessionId: 'first-session' }, { certNumber: 'P0001', sessionId: 'second-session' }],
    ['P0001', 'P0002']
  ]) {
    it(`print-center reprint preserves ${typeof references[0] === 'string' ? 'legacy numbers' : 'both sessions'} through both requests`, async () => {
      const { calls, env } = printIO()
      Object.assign(env, { parsePrintReferences, printReferenceKey, printReferenceNumber })
      const view = execute(pick('PrintCenterView', 'const DOC_TYPE_LABELS =', 'onMounted(loadLogs)'), env, 'reprint,refIdsOf')
      const log = { id: 'old-log', template_id: 'template', title: 'Original print', ref_ids: JSON.stringify(references) }
      assert.deepEqual(view.refIdsOf(log), references)
      await view.reprint(log)
      assert.deepEqual(calls.errors, [])
      assert.deepEqual(calls.generated, [{ templateId: 'template', certNumbers: references }])
      assert.deepEqual(calls.archived[0].refIds, references)
      assert.equal(calls.opened.length, 1)
    })
  }

  it('certificate history separates matching sessions and unassigned legacy history', async () => {
    const first = { certNumber: 'P0001', sessionId: 'first-session' }
    const second = { certNumber: 'P0001', sessionId: 'second-session' }
    const logs = [
      { ref_ids: JSON.stringify([first]), printed_at: '2026-10-01', title: 'First' },
      { ref_ids: JSON.stringify([second]), printed_at: '2026-10-02', title: 'Second' },
      { ref_ids: JSON.stringify(['P0001']), printed_at: '2026-09-01', title: 'Legacy' },
      { ref_ids: '{broken', printed_at: '2026-10-03', title: 'Invalid' }
    ]
    const env = { printLogIndex: ref({}), indexPrintReferences, printReferenceKey,
      fetchPrintLogs: async () => ({ success: true, logs }) }
    const view = execute(pick('CertificatesView', 'const loadPrintIndex =', 'onMounted(async'), env,
      'loadPrintIndex,printHist,legacyPrintHist')
    await view.loadPrintIndex()
    assert.deepEqual(view.printHist(first), { count: 1, last: '2026-10-01', title: 'First' })
    assert.deepEqual(view.printHist(second), { count: 1, last: '2026-10-02', title: 'Second' })
    assert.equal(view.printHist({ certNumber: 'P0001', sessionId: 'never-printed' }), undefined)
    assert.deepEqual(view.legacyPrintHist(first), { count: 1, last: '2026-09-01', title: 'Legacy' })
    assert.equal(view.legacyPrintHist(first), view.legacyPrintHist(second))
  })
})
