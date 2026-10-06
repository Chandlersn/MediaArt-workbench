import fs from 'node:fs'
import assert from 'node:assert/strict'
import { ref } from 'vue'
import { createPinia, defineStore, setActivePinia } from 'pinia'

const clone = value => JSON.parse(JSON.stringify(value))
const quietConsole = { error() {}, warn() {}, log() {} }
const cases = [
  { file: 'project', factory: 'useProjectStore', key: 'projects', list: 'projects', load: 'loadProjects', save: 'saveProject', remove: 'deleteProject', select: 'setCurrentProject', current: 'currentProject' },
  { file: 'player', factory: 'usePlayerStore', key: 'players', list: 'players', load: 'loadPlayers', save: 'savePlayer', remove: 'deletePlayer', select: 'setCurrentPlayer', current: 'currentPlayer' },
  { file: 'organization', factory: 'useOrganizationStore', key: 'organizations', list: 'organizations', load: 'loadOrganizations', save: 'saveOrganization', remove: 'deleteOrganization', select: 'setCurrentOrganization', current: 'currentOrganization' },
  { file: 'finance', factory: 'useFinanceStore', key: 'finances', list: 'financeRecords', load: 'loadRecords', save: 'saveRecord', remove: 'deleteRecord', select: 'setCurrentFinance', current: 'currentFinance' }
]

function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

function fixture(spec) {
  setActivePinia(createPinia())
  let state = [
    { id: 'a', name: 'Original A', title: 'Original A', amount: 10 },
    { id: 'b', name: 'Original B', title: 'Original B', amount: 20 }
  ]
  let revision = 'r1'
  let pending
  const service = {
    attempts: [], loads: 0, nextError: null, nextGate: null, auditError: null,
    async load() { service.loads++ },
    getData: () => clone(state),
    getRevision: () => revision,
    setData(key, value, expected) { pending = { key, value: clone(value), expected } },
    async save() {
      const batch = pending
      pending = null
      service.attempts.push(batch)
      const failure = service.nextError
      const gate = service.nextGate
      service.nextError = null
      service.nextGate = null
      if (gate) {
        gate.started.resolve()
        await gate.release.promise
      }
      if (failure) throw failure
      assert.equal(batch.expected, revision, 'store must advance its own revision after successful saves')
      state = clone(batch.value)
      revision = `r${Number(revision.slice(1)) + 1}`
      return { success: true, _revisions: { [spec.key]: revision } }
    },
    delayNextSave() {
      const gate = { started: deferred(), release: deferred() }
      service.nextGate = gate
      return gate
    }
  }
  const source = fs.readFileSync(new URL(`../../src/stores/${spec.file}.js`, import.meta.url), 'utf8')
    .replace(/^import .*$/mg, '').replace(/^export /mg, '')
  const factory = new Function('defineStore', 'ref', 'dataService', 'useAuditLogStore', 'get', 'console',
    `${source}\nreturn ${spec.factory};`)
  const store = factory(defineStore, ref, service, () => ({ async addLog() {
    if (service.auditError) throw service.auditError
  } }), async () => ({}), quietConsole)()
  return { store, service, server: () => clone(state) }
}

describe('Store mutations only become visible after successful persistence', () => {
  for (const spec of cases) {
    it(`${spec.file}: failed create preserves its input and does not duplicate a retry`, async () => {
      const { store, service, server } = fixture(spec)
      await store[spec.load]()
      const originalList = store[spec.list]
      const before = clone(originalList)
      const input = { name: 'New record', title: 'New record', amount: 30, nested: { keep: true } }
      const originalInput = clone(input)
      service.nextError = new Error('save unavailable')
      await assert.rejects(store[spec.save](input), /save unavailable/)
      assert.equal(store[spec.list], originalList)
      assert.deepEqual(clone(store[spec.list]), before)
      assert.deepEqual(input, originalInput)
      assert.deepEqual(server(), before)
      const saved = await store[spec.save](input)
      assert.ok(saved.id)
      assert.equal(store[spec.list].length, 3)
      assert.equal(server().filter(row => row.name === 'New record').length, 1)
      assert.deepEqual(input, originalInput)
    })

    it(`${spec.file}: a failed edit is absent from the next successful edit`, async () => {
      const { store, service, server } = fixture(spec)
      await store[spec.load]()
      store[spec.select](store[spec.list][0])
      const selected = store[spec.current]
      const originalList = store[spec.list]
      const input = { id: 'a', name: 'Rejected edit', amount: 99 }
      service.nextError = new Error('revision conflict')
      await assert.rejects(store[spec.save](input), /revision conflict/)
      assert.equal(store[spec.list], originalList)
      assert.equal(store[spec.current], selected)
      assert.deepEqual(input, { id: 'a', name: 'Rejected edit', amount: 99 })
      assert.equal(store.error, 'revision conflict')
      await store[spec.save]({ id: 'b', name: 'Accepted edit' })
      assert.equal(server().find(row => row.id === 'a').name, 'Original A')
      assert.equal(server().find(row => row.id === 'a').amount, 10)
      assert.equal(server().find(row => row.id === 'b').name, 'Accepted edit')
      assert.equal(store.error, null)
    })

    it(`${spec.file}: failed deletion preserves the list and current selection`, async () => {
      const { store, service, server } = fixture(spec)
      await store[spec.load]()
      store[spec.select](store[spec.list][0])
      const selected = store[spec.current]
      const originalList = store[spec.list]
      service.nextError = new Error('delete rejected')
      await assert.rejects(store[spec.remove]('a'), /delete rejected/)
      assert.equal(store[spec.list], originalList)
      assert.equal(store[spec.current], selected)
      await store[spec.save]({ id: 'b', name: 'Later edit' })
      assert.equal(server().length, 2)
      assert.equal(server().find(row => row.id === 'a').name, 'Original A')
      await store[spec.remove]('a')
      assert.equal(server().length, 1)
      assert.equal(store[spec.current], null)
    })

    it(`${spec.file}: concurrent edits are built serially from confirmed state`, async () => {
      const { store, service, server } = fixture(spec)
      await store[spec.load]()
      const before = clone(store[spec.list])
      const gate = service.delayNextSave()
      const first = store[spec.save]({ id: 'a', name: 'First confirmed' })
      await gate.started.promise
      const second = store[spec.save]({ id: 'b', name: 'Second confirmed' })
      await Promise.resolve()
      await Promise.resolve()
      assert.equal(service.attempts.length, 1)
      assert.deepEqual(clone(store[spec.list]), before)
      gate.release.resolve()
      await Promise.all([first, second])
      assert.equal(server().find(row => row.id === 'a').name, 'First confirmed')
      assert.equal(server().find(row => row.id === 'b').name, 'Second confirmed')
      assert.deepEqual(service.attempts.map(batch => batch.expected), ['r1', 'r2'])
    })

    it(`${spec.file}: a rejected queued edit cannot leak into the following save`, async () => {
      const { store, service, server } = fixture(spec)
      await store[spec.load]()
      const gate = service.delayNextSave()
      service.nextError = new Error('first failed')
      const first = assert.rejects(store[spec.save]({ id: 'a', name: 'Must not persist' }), /first failed/)
      await gate.started.promise
      const second = store[spec.save]({ id: 'b', name: 'Must persist' })
      gate.release.resolve()
      await Promise.all([first, second])
      assert.equal(server().find(row => row.id === 'a').name, 'Original A')
      assert.equal(server().find(row => row.id === 'b').name, 'Must persist')
      assert.deepEqual(service.attempts.map(batch => batch.expected), ['r1', 'r1'])
    })

    it(`${spec.file}: reload waits for pending saves and preserves the committed revision`, async () => {
      const { store, service, server } = fixture(spec)
      await store[spec.load]()
      const gate = service.delayNextSave()
      const save = store[spec.save]({ id: 'a', name: 'Confirmed before reload' })
      await gate.started.promise
      const reload = store[spec.load]()
      const followingSave = store[spec.save]({ id: 'b', name: 'Confirmed after reload' })
      await Promise.resolve()
      await Promise.resolve()
      assert.equal(service.loads, 1, 'reload must wait until the pending mutation finishes')
      gate.release.resolve()
      await Promise.all([save, reload, followingSave])
      assert.equal(service.loads, 2)
      assert.equal(store[spec.list].find(row => row.id === 'a').name, 'Confirmed before reload')
      assert.equal(server().find(row => row.id === 'b').name, 'Confirmed after reload')
      assert.deepEqual(service.attempts.map(batch => batch.expected), ['r1', 'r2'])
    })

    it(`${spec.file}: audit failure does not undo a successful business save`, async () => {
      const { store, service, server } = fixture(spec)
      service.auditError = new Error('audit unavailable')
      await store[spec.save]({ id: 'a', name: 'Saved' })
      assert.equal(server().find(row => row.id === 'a').name, 'Saved')
      assert.equal(store[spec.list].find(row => row.id === 'a').name, 'Saved')
      assert.equal(store.error, null)
    })
  }
})
