import fs from 'node:fs'
import assert from 'node:assert/strict'
import { ref, computed, watch } from 'vue'
import { createPinia, defineStore, setActivePinia } from 'pinia'

// Execute the production script bodies with real Vue/Pinia and isolated I/O.
const read = path => fs.readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8')
const stripImports = source => source.replace(/^import .*$/mg, '').replace(/^export /mg, '')
const clone = value => JSON.parse(JSON.stringify(value))
const quietConsole = { error() {}, warn() {}, log() {} }

function fixture(initial = {}) {
  const state = {
    projects: [{ id: 'p1', name: 'Original project', type: 'exhibition' }],
    organizations: [{ id: 'o1', name: 'Original organization' }],
    players: [{ id: 'pl1', name: 'Original player', category: 'music' }],
    finances: [{ id: 'f1', type: 'income', amount: 100 }],
    knowledge: { guide: [{ id: 'k1', title: 'Original knowledge', type: 'guide' }] },
    certificates: [{ certNumber: 'C1', sessionId: 's1' }],
    certSettings: {},
    ...initial
  }
  const revisions = Object.fromEntries(Object.keys(state).map(key => [key, 1]))
  const pending = new Map()
  const service = {
    failLoad: false, failSave: false, loads: 0, saves: 0, writes: [], revisions,
    async load() {
      service.loads++
      if (service.failLoad) throw new Error('load unavailable')
    },
    getData: key => clone(state[key] ?? []),
    getRevision: key => revisions[key],
    setData(key, value, revision) {
      service.writes.push({ key, value: clone(value), revision })
      pending.set(key, { value: clone(value), revision })
    },
    async save() {
      if (service.failSave) throw new Error('save unavailable')
      for (const [key, item] of pending) {
        if (item.revision !== revisions[key]) throw new Error('revision conflict')
      }
      service.saves++
      for (const [key, item] of pending) {
        state[key] = item.value
        revisions[key]++
      }
      pending.clear()
      return { success: true, _revisions: { ...revisions } }
    }
  }
  return { service, state }
}

function loadStore(file, name, service) {
  const factory = new Function('defineStore', 'ref', 'computed', 'dataService', 'useAuditLogStore', 'get', 'console',
    `${stripImports(read(`src/stores/${file}.js`))}\nreturn ${name};`)
  return factory(defineStore, ref, computed, service, () => ({ addLog: async () => {} }), async () => ({}), quietConsole)()
}

const storeCases = [
  ['organization', 'useOrganizationStore', 'organizations', 'loadOrganizations', 'addOrganization', { name: 'New organization' }],
  ['finance', 'useFinanceStore', 'finances', 'loadRecords', 'saveRecord', { amount: 5 }],
  ['project', 'useProjectStore', 'projects', 'loadProjects', 'saveProject', { name: 'New project' }],
  ['player', 'usePlayerStore', 'players', 'loadPlayers', 'savePlayer', { name: 'New player' }],
  ['knowledge', 'useKnowledgeStore', 'knowledge', 'loadItems', 'saveItem', { title: 'New knowledge', type: 'guide' }],
  ['certificate', 'useCertificateStore', 'certificates', 'loadCertificates', 'saveCert', { certNumber: 'C2', sessionId: 's1' }]
]

describe('Frontend data-loss regressions', () => {
  for (const [file, name, key, loader, writer, payload] of storeCases) {
    it(`${file}: cold writes load existing records and keep them`, async () => {
      setActivePinia(createPinia())
      const { service, state } = fixture()
      const store = loadStore(file, name, service)
      await store[writer](clone(payload))
      assert.equal(service.loads, 1)
      assert.equal(store.loaded, true)
      assert.equal(service.writes[0].revision, 1)
      assert.equal((key === 'knowledge' ? state[key].guide : state[key]).length, 2)
    })

    it(`${file}: failed loads never submit or mutate a record`, async () => {
      setActivePinia(createPinia())
      const { service } = fixture()
      service.failLoad = true
      const store = loadStore(file, name, service)
      assert.equal(await store[loader](), false)
      const input = clone(payload)
      await assert.rejects(store[writer](input), /load unavailable/)
      assert.deepEqual(input, payload)
      assert.equal(store.loaded, false)
      assert.equal(service.writes.length, 0)
      assert.equal(service.saves, 0)
    })

    it(`${file}: a newer shared snapshot cannot refresh an old store's revision`, async () => {
      setActivePinia(createPinia())
      const { service } = fixture()
      const store = loadStore(file, name, service)
      await store[loader]()
      service.revisions[key] = 2
      await assert.rejects(store[writer](clone(payload)), /revision conflict/)
      assert.equal(service.writes[0].revision, 1)
      assert.equal(service.saves, 0)
    })
  }

  it('successful writes advance the store revision for subsequent saves', async () => {
    setActivePinia(createPinia())
    const { service } = fixture()
    const store = loadStore('project', 'useProjectStore', service)
    await store.saveProject({ id: 'p1', name: 'First edit' })
    await store.saveProject({ id: 'p1', name: 'Second edit' })
    assert.deepEqual(service.writes.map(write => write.revision), [1, 2])
  })

  it('moving knowledge to another type preserves its ID and updated content', async () => {
    setActivePinia(createPinia())
    const { service, state } = fixture()
    const store = loadStore('knowledge', 'useKnowledgeStore', service)
    await store.updateItem('k1', { type: 'tip', title: 'Edited', fields: { point: 'Useful' } })
    assert.deepEqual(state.knowledge.guide, [])
    assert.equal(state.knowledge.tip.length, 1)
    assert.equal(state.knowledge.tip[0].id, 'k1')
    assert.equal(state.knowledge.tip[0].title, 'Edited')
    assert.deepEqual(state.knowledge.tip[0].fields, { point: 'Useful' })
  })

  it('updating missing knowledge reports an error without writing', async () => {
    setActivePinia(createPinia())
    const { service } = fixture()
    const store = loadStore('knowledge', 'useKnowledgeStore', service)
    await assert.rejects(store.updateItem('missing', { type: 'tip', title: 'Edited' }))
    assert.equal(service.saves, 0)
  })

  it('rejects constant certificate templates before changing settings', async () => {
    setActivePinia(createPinia())
    const { service } = fixture()
    const store = loadStore('certificate', 'useCertificateStore', service)
    await store.loadCertificates()
    const before = clone(store.certSettings)
    await assert.rejects(store.updateTemplateSettings({ templates: { province: 'FIXED' } }), /seq/)
    assert.deepEqual(clone(store.certSettings), before)
    assert.equal(service.saves, 0)
  })

  it('rejects a legacy constant template before synchronizing players', async () => {
    setActivePinia(createPinia())
    const { service, state } = fixture({ certSettings: { templates: { province: 'FIXED', national: 'Q{seq}' } } })
    const store = loadStore('certificate', 'useCertificateStore', service)
    await assert.rejects(store.syncFromPlayers([{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }], [], { assignNumbers: true }), /seq/)
    assert.equal(service.saves, 0)
    assert.equal(state.certificates.length, 1)
  })

  it('generates unique certificate numbers and updates both section revisions', async () => {
    setActivePinia(createPinia())
    const { service, state } = fixture({ certificates: [], certSettings: { templates: { province: 'P{seq:4}', national: 'Q{seq}' } } })
    const store = loadStore('certificate', 'useCertificateStore', service)
    await store.syncFromPlayers([{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }], [], { assignNumbers: true })
    assert.deepEqual(state.certificates.map(item => item.certNumber), ['P0001', 'P0002'])
    await store.updateTemplateSettings({ templates: { province: 'P{seq:5}' } })
    assert.equal(service.writes.at(-1).revision, 2)
  })

  it('failed knowledge creation leaves no draft record or assigned ID and can be retried', async () => {
    setActivePinia(createPinia())
    const { service, state } = fixture()
    const knowledge = loadStore('knowledge', 'useKnowledgeStore', service)
    await knowledge.loadItems()
    const input = { type: 'guide', title: 'New item' }
    service.failSave = true
    await assert.rejects(knowledge.saveItem(input), /save unavailable/)
    assert.equal(knowledge.knowledge.guide.length, 1)
    assert.equal(input.id, undefined)
    assert.equal(knowledge.loaded, false)
    service.failSave = false
    await knowledge.saveItem(input)
    assert.equal(state.knowledge.guide.length, 2)
    assert.equal(service.loads, 2)
  })

  it('failed knowledge type migration restores both buckets', async () => {
    setActivePinia(createPinia())
    const { service } = fixture()
    const knowledge = loadStore('knowledge', 'useKnowledgeStore', service)
    await knowledge.loadItems()
    service.failSave = true
    await assert.rejects(knowledge.updateItem('k1', { type: 'tip', title: 'Moved' }), /save unavailable/)
    assert.equal(knowledge.knowledge.guide[0].title, 'Original knowledge')
    assert.deepEqual(knowledge.knowledge.tip, [])
  })

  it('knowledge concurrent changes serialize mutations and advance revisions', async () => {
    setActivePinia(createPinia())
    const { service, state } = fixture()
    const knowledge = loadStore('knowledge', 'useKnowledgeStore', service)
    await Promise.all([
      knowledge.updateItem('k1', { type: 'guide', title: 'Edited title' }),
      knowledge.updateItem('k1', { type: 'guide', description: 'Edited description' })
    ])
    assert.equal(state.knowledge.guide[0].title, 'Edited title')
    assert.equal(state.knowledge.guide[0].description, 'Edited description')
    assert.deepEqual(service.writes.map(item => item.revision), [1, 2])
  })

  it('failed certificate import restores certificates, settings and active session before retry', async () => {
    setActivePinia(createPinia())
    const { service, state } = fixture()
    const certificate = loadStore('certificate', 'useCertificateStore', service)
    await certificate.loadCertificates()
    const before = clone({ certificates: certificate.certificates, settings: certificate.certSettings, active: certificate.activeSessionId })
    service.failSave = true
    await assert.rejects(certificate.importCertificates([{ certNumber: 'C2' }], { fileName: 'test' }), /save unavailable/)
    assert.deepEqual(clone({ certificates: certificate.certificates, settings: certificate.certSettings, active: certificate.activeSessionId }), before)
    assert.equal(certificate.lastImport, null)
    service.failSave = false
    await certificate.importCertificates([{ certNumber: 'C2' }], { fileName: 'test' })
    assert.equal(state.certificates.length, 2)
    assert.equal(Object.keys(state.certSettings.sessionMeta).length, 1)
    assert.equal(certificate.lastImport.count, 1)
  })

  it('failed certificate synchronization restores existing identities and does not consume numbers', async () => {
    setActivePinia(createPinia())
    const { service, state } = fixture({
      certificates: [{ certNumber: 'P0001', sessionId: 's1', playerId: 'a', playerName: 'Original', certRound: 'province' }],
      certSettings: { templates: { province: 'P{seq:4}', national: 'Q{seq}' } }
    })
    const certificate = loadStore('certificate', 'useCertificateStore', service)
    await certificate.loadCertificates()
    const players = [{ id: 'a', name: 'Edited' }, { id: 'b', name: 'New player' }]
    service.failSave = true
    await assert.rejects(certificate.syncFromPlayers(players, [], { assignNumbers: true, certRound: 'province' }), /save unavailable/)
    assert.equal(certificate.certificates.length, 1)
    assert.equal(certificate.certificates[0].playerName, 'Original')
    assert.deepEqual(certificate.certSettings.sessionMeta, {})
    service.failSave = false
    await certificate.syncFromPlayers(players, [], { assignNumbers: true, certRound: 'province' })
    assert.deepEqual(state.certificates.map(item => item.certNumber), ['P0001', 'P0002'])
    assert.equal(state.certificates[0].playerName, 'Edited')
  })

  it('failed certificate session deletion restores both persisted sections', async () => {
    setActivePinia(createPinia())
    const { service } = fixture()
    const certificate = loadStore('certificate', 'useCertificateStore', service)
    await certificate.loadCertificates()
    const before = clone({ certificates: certificate.certificates, settings: certificate.certSettings })
    service.failSave = true
    await assert.rejects(certificate.deleteSession('s1'), /save unavailable/)
    assert.deepEqual(clone({ certificates: certificate.certificates, settings: certificate.certSettings }), before)
    assert.equal(certificate.activeSessionId, 's1')
  })

  it('certificate concurrent edits serialize and a queued reload sees the committed values', async () => {
    setActivePinia(createPinia())
    const { service, state } = fixture()
    const certificate = loadStore('certificate', 'useCertificateStore', service)
    await Promise.all([
      certificate.updateCert('C1', { playerName: 'Edited' }, 's1'),
      certificate.updateCert('C1', { award: 'Gold' }, 's1'),
      certificate.loadCertificates()
    ])
    assert.equal(state.certificates[0].playerName, 'Edited')
    assert.equal(state.certificates[0].award, 'Gold')
    assert.equal(certificate.certificates[0].award, 'Gold')
    assert.deepEqual(service.writes.map(item => item.revision), [1, 2])
  })
})

function loadForm(file, stores, params = {}) {
  let mounted
  const messages = []
  const toast = { success() {}, warning() {}, error: message => messages.push(message) }
  const env = {
    ref, computed, watch,
    onMounted: fn => { mounted = fn },
    useRouter: () => ({ push() {} }),
    useRoute: () => ({ params, query: {} }),
    useProjectStore: () => stores.project,
    usePlayerStore: () => stores.player,
    useOrganizationStore: () => stores.organization,
    useFinanceStore: () => stores.finance,
    useToast: () => toast, useMessage: () => toast,
    required() {}, phone() {}, idCard() {}, positiveNumber() {},
    validate: () => ({ valid: true }), console: quietConsole
  }
  const source = read(`src/views/${file}FormView.vue`).match(/<script setup>([\s\S]*?)<\/script>/)[1]
  const form = new Function(...Object.keys(env), `${stripImports(source)}\nreturn {formData, formReady, handleSave};`)(...Object.values(env))
  return { ...form, mount: () => mounted(), messages }
}

function formStores(service) {
  return Object.fromEntries(storeCases.slice(0, 4).map(([file, name]) => [file, loadStore(file, name, service)]))
}

describe('Production form regressions', () => {
  for (const [formName, storeName, key, id] of [['Project', 'project', 'projects', 'p1'], ['Player', 'player', 'players', 'pl1']]) {
    it(`${formName}: direct edit waits for load and updates the original ID`, async () => {
      setActivePinia(createPinia())
      const { service, state } = fixture()
      const form = loadForm(formName, formStores(service), { id })
      assert.equal(form.formReady.value, false)
      await form.mount()
      assert.equal(form.formData.value.id, id)
      assert.equal(form.formReady.value, true)
      form.formData.value.name = 'Edited'
      await form.handleSave()
      assert.equal(state[key].length, 1)
      assert.equal(state[key][0].id, id)
      assert.equal(state[key][0].name, 'Edited')
      assert.deepEqual(form.messages, [])
    })
  }

  for (const [formName, key] of [['Organization', 'organizations'], ['Finance', 'finances']]) {
    it(`${formName}: direct new form preserves existing data`, async () => {
      setActivePinia(createPinia())
      const { service, state } = fixture()
      const form = loadForm(formName, formStores(service))
      await form.mount()
      form.formData.value.name = 'New'
      await form.handleSave()
      assert.equal(state[key].length, 2)
      assert.deepEqual(form.messages, [])
    })

    it(`${formName}: load failure is visible and save stays disabled`, async () => {
      setActivePinia(createPinia())
      const { service } = fixture()
      service.failLoad = true
      const form = loadForm(formName, formStores(service))
      await form.mount()
      assert.equal(form.formReady.value, false)
      assert.equal(form.messages.length, 1)
      await form.handleSave()
      assert.equal(service.saves, 0)
    })
  }
})
