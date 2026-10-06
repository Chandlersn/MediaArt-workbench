import fs from 'node:fs'
import assert from 'node:assert/strict'
import { ref, computed, reactive, watch } from 'vue'
import { defineStore, createPinia, setActivePinia } from 'pinia'

const read = path => fs.readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8')
const strip = text => text.replace(/^import .*$/mg, '').replace(/^export /mg, '')
const clone = value => JSON.parse(JSON.stringify(value))
const quietConsole = { error() {}, warn() {} }

function materialsWorkflow(playerOverrides = {}) {
  setActivePinia(createPinia())
  const player = { id: 'p1', name: 'Player', stage: 'Final', orgId: 'org1', ...playerOverrides }
  const state = {
    players: [player], config: { stageMaterials: { Final: ['ID'] } },
    materialTypes: [{ name: 'ID' }],
    _revisions: { players: 'p1', config: 'c1', materialTypes: 'm1' }
  }
  const io = { materials: [], scanFails: false, scanCalls: 0, loadGate: null, requests: [], loadStarted: null }
  const get = async url => {
    if (url === '/api/data/load') {
      io.loadStarted?.()
      if (io.loadGate) await io.loadGate
      return { success: true, data: clone(state) }
    }
    if (url.startsWith('/api/scan-player-files?')) {
      io.scanCalls++
      if (io.scanFails) throw new Error('scan unavailable')
      return { success: true, materials: clone(io.materials) }
    }
    throw new Error(`unexpected GET ${url}`)
  }
  const dataService = new Function('get', 'post', `${strip(read('src/services/dataService.js'))}
    return {load,getData,getRevision,setData,save,isLoaded};`)(get, async () => { throw new Error('unexpected data write') })
  const module = new Function('defineStore', 'ref', 'dataService', 'useAuditLogStore', 'get', 'console',
    `${strip(read('src/stores/player.js'))}\nreturn {usePlayerStore,resolvePlayerMaterialStatus};`)(
    defineStore, ref, dataService, () => ({ addLog: async () => {} }), get, quietConsole)
  const store = module.usePlayerStore()
  return { state, io, dataService, store, resolve: module.resolvePlayerMaterialStatus }
}

function detailView(workflow) {
  const { store, dataService, io } = workflow
  let mount
  const messages = { success: [], error: [] }
  const env = {
    ref, computed, reactive, watch,
    onMounted: fn => { mount = fn }, onActivated() {},
    useRoute: () => ({ params: { id: 'p1' } }), useRouter: () => ({ push() {} }),
    usePlayerStore: () => store,
    useProjectStore: () => ({ loadProjects: async () => {}, getProjectById: () => null }),
    useOrganizationStore: () => ({ loadOrganizations: async () => {}, getOrgById: () => null }),
    useToast: () => ({ success: text => messages.success.push(text), error: text => messages.error.push(text), warning() {} }),
    useConfirmDialog: () => ({ confirm: async () => true }), dataService,
    FormData: class {
      constructor() { this.values = new Map() }
      append(key, value) { this.values.set(key, value) }
      get(key) { return this.values.get(key) }
    },
    fetchWithAuth: async (url, options) => {
      if (url === '/api/upload') {
        io.requests.push({ url, type: options.body.get('materialType'), playerName: options.body.get('playerName') })
        io.materials = [{ type: options.body.get('materialType'), file_name: 'id.pdf', name: 'id.pdf', upload_date: '2026-10-05', stage: options.body.get('stage') || '' }]
      } else if (url === '/api/delete-player-material') {
        io.requests.push({ url, ...JSON.parse(options.body) })
        io.materials = []
      } else throw new Error(`unexpected request ${url}`)
      return { json: async () => ({ success: true }) }
    },
    getBlob: async () => {}, console: quietConsole
  }
  const script = read('src/views/PlayerDetailView.vue').match(/<script setup>([\s\S]*?)<\/script>/)[1]
  const view = new Function(...Object.keys(env), `${strip(script)}
    return {player,missingMaterials,materialType,selectedFile,uploadMaterial,deleteMaterial,detailLoading,loadPlayerMaterials};`)(...Object.values(env))
  return { ...view, mount: () => mount(), messages }
}

describe('Player material workflow', () => {
  it('exact upload classification satisfies a required form without treating its archive category as equivalent', () => {
    const { resolve } = materialsWorkflow()
    const player = { stage: '初赛' }
    const config = { 初赛: ['报名表'] }
    const coarse = resolve(player, config, [], { success: true, materials: [
      { type: '个人信息', file_name: '选手_初赛__扫描件.pdf', stage: '初赛' }
    ] })
    assert.deepEqual(coarse.missingTypes, ['报名表'])
    const exact = resolve(player, config, [], { success: true, materials: [
      { type: '报名表', file_name: '选手_初赛__扫描件.pdf', stage: '初赛' }
    ] })
    assert.deepEqual(exact.missingTypes, [])
  })

  it('scan materials use only the current stage or common files and respect organization-specific requirements', () => {
    const { resolve } = materialsWorkflow()
    const result = resolve({ stage: 'Final', orgId: 'org1' }, { Final: ['ID', 'Video', 'Common', 'OtherOrg'] },
      [{ name: 'OtherOrg', orgId: 'org2' }], { success: true, materials: [
        { type: 'ID', stage: 'Initial' }, { type: 'Video', stage: 'Final' }, { type: 'Common' }
      ] })
    assert.deepEqual(result.missingTypes, ['ID'])
    assert.deepEqual(result.requiredTypes, ['ID', 'Video', 'Common'])
  })

  it('a successful empty scan is authoritative even when history claims a document exists', () => {
    const { resolve } = materialsWorkflow()
    const result = resolve({ stage: 'Final', history: [{ stage: 'Final', materials: [{ type: 'ID' }] }] },
      { Final: ['ID'] }, [], { success: true, materials: [], message: 'directory does not exist' })
    assert.equal(result.scanned, true)
    assert.deepEqual(result.materials, [])
    assert.deepEqual(result.missingTypes, ['ID'])
  })

  it('failed scans fall back to history while excluding explicitly different stages', () => {
    const { resolve } = materialsWorkflow()
    const result = resolve({ stage: 'Final', history: [{ stage: 'Final', materials: [{ type: 'ID' }, { type: 'Video', stage: 'Initial' }] }] },
      { Final: ['ID', 'Video'] }, [], { success: false })
    assert.equal(result.scanned, false)
    assert.deepEqual(result.missingTypes, ['Video'])
    assert.equal(result.materials[0].stage, 'Final')
  })

  it('store reminders consume materials arrays and a reload invalidates the five-second cache', async () => {
    const { store, io } = materialsWorkflow()
    io.materials = [{ type: 'ID', file_name: 'id.pdf', stage: 'Final' }]
    assert.equal(await store.getMissingMaterialsCount(), 0)
    io.materials = []
    await store.loadPlayers()
    assert.equal(await store.getMissingMaterialsCount(), 1)
    assert.equal(io.scanCalls, 2)
  })

  it('scan transport failure uses historical materials without claiming an authoritative empty result', async () => {
    const { store, io } = materialsWorkflow({ history: [{ stage: 'Final', materials: [{ type: 'ID', name: 'historical.pdf' }] }] })
    io.scanFails = true
    assert.equal(await store.getMissingMaterialsCount(), 0)
    assert.equal(store.players[0].materials[0].name, 'historical.pdf')
  })

  it('the list and reminder paths share scan results rather than separate historical algorithms', async () => {
    const workflow = materialsWorkflow({ history: [{ stage: 'Final', materials: [{ type: 'ID' }] }] })
    const list = clone(workflow.state.players)
    const source = read('src/views/PlayersView.vue')
    const helper = source.slice(source.indexOf('const computeMissingMaterials ='), source.indexOf('const filteredAllPlayers ='))
    const compute = new Function('dataService', 'playerStore', `${helper}\nreturn computeMissingMaterials;`)(workflow.dataService, workflow.store)
    assert.equal(await compute(list), 1)
    assert.equal(list[0].missingCount, 1)
    assert.deepEqual(list[0].materials, [])
    assert.equal(await workflow.store.getMissingMaterialsCount(), 1)
  })

  it('cold detail waits for the player before requesting its materials', async () => {
    const workflow = materialsWorkflow()
    let release
    let started
    workflow.io.loadGate = new Promise(resolve => { release = resolve })
    const whenStarted = new Promise(resolve => { started = resolve })
    workflow.io.loadStarted = started
    workflow.io.materials = [{ type: 'ID', file_name: 'id.pdf', upload_date: '2026-10-05', stage: 'Final' }]
    const view = detailView(workflow)
    const loading = view.mount()
    await whenStarted
    assert.equal(workflow.io.scanCalls, 0)
    assert.equal(view.player.value, undefined)
    release()
    await loading
    assert.equal(workflow.io.scanCalls, 1)
    assert.equal(view.player.value.materials[0].name, 'id.pdf')
    assert.equal(view.player.value.materials[0].uploadDate, '2026-10-05')
    assert.deepEqual(view.missingMaterials.value, [])
    assert.equal(view.detailLoading.value, false)
    assert.deepEqual(view.messages.error, [])
  })

  it('detail upload and object-based deletion immediately recompute missing materials', async () => {
    const workflow = materialsWorkflow({ history: [{ stage: 'Final', materials: [{ type: 'ID' }] }] })
    const view = detailView(workflow)
    await view.mount()
    assert.deepEqual(view.missingMaterials.value, ['ID'])
    view.materialType.value = 'ID'
    view.selectedFile.value = { name: 'id.pdf' }
    await view.uploadMaterial()
    assert.deepEqual(view.missingMaterials.value, [])
    assert.equal(view.player.value.materials.length, 1)
    assert.equal(await workflow.store.getMissingMaterialsCount(), 0)
    await view.deleteMaterial(view.player.value.materials[0])
    assert.equal(workflow.io.requests[1].fileName, 'id.pdf')
    assert.deepEqual(view.player.value.materials, [])
    assert.deepEqual(view.missingMaterials.value, ['ID'])
    assert.equal(await workflow.store.getMissingMaterialsCount(), 1)
    assert.deepEqual(view.messages.error, [])
    assert.equal(view.messages.success.length, 2)
  })
})
