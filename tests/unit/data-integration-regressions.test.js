import fs from 'node:fs'
import assert from 'node:assert/strict'
import { ref, computed } from 'vue'
import { defineStore, setActivePinia, createPinia } from 'pinia'
import * as checklistModel from '../../src/stores/checklistModel.js'

const read = path => fs.readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8')
const strip = text => text.replace(/^import .*$/mg, '').replace(/^export /mg, '')
const clone = value => JSON.parse(JSON.stringify(value))
const quietConsole = { error() {}, warn() {} }

function integration() {
  const server = {
    config: { resourceCategories: [{ id: 'a', name: 'A', folder: 'a' }], preserved: 'value' },
    projectChecklists: { __global__: { startup: { label: 'Start', cards: [
      { id: 'c1', title: 'Card', items: [{ text: 'A', checked: false }, { text: 'B', checked: false }] }
    ] } } },
    projects: [{ id: 'p1', name: 'Original' }],
    _revisions: { config: 'v1', projectChecklists: 'v1', projects: 'v1' }
  }
  const control = { failLoad: false, failSave: false, loads: 0, payloads: [] }
  const get = async () => {
    control.loads++
    if (control.failLoad) throw new Error('load unavailable')
    return { success: true, data: clone(server) }
  }
  const post = async (_, payload) => {
    control.payloads.push(clone(payload))
    if (control.failSave) throw new Error('save unavailable')
    for (const key of Object.keys(payload._revisions)) {
      if (payload._revisions[key] !== server._revisions[key]) throw new Error('revision conflict')
    }
    for (const key of Object.keys(payload._revisions)) {
      server[key] = clone(payload[key])
      server._revisions[key] += '+'
    }
    return { success: true, _revisions: clone(server._revisions) }
  }
  const dataService = new Function('get', 'post', `${strip(read('src/services/dataService.js'))}
    return {load,getData,getRevision,setData,save};`)(get, post)
  return { dataService, server, control }
}

function store(file, name, dataService) {
  setActivePinia(createPinia())
  const env = {
    ref, computed, defineStore, dataService, ...checklistModel,
    useAuditLogStore: () => ({ addLog: async () => {} }), console: quietConsole
  }
  return new Function(...Object.keys(env), `${strip(read(`src/stores/${file}.js`))}\nreturn ${name}();`)(...Object.values(env))
}

function settingsCategories(dataService) {
  const text = read('src/views/SettingsView.vue')
  const section = text.slice(text.indexOf('let categoriesRevision ='), text.indexOf('const importData ='))
  const errors = []
  const env = {
    dataService, resourceCategories: ref([]), newCategory: ref({}),
    editingCategoryIndex: ref(-1), showCategoryModal: ref(true),
    error: message => errors.push(message), console: quietConsole
  }
  const actions = new Function(...Object.keys(env), `${section}\nreturn {loadResourceCategories,saveCategory,removeCategory};`)(...Object.values(env))
  return { ...env, ...actions, errors }
}

describe('Data service integration regressions', () => {
  it('settings category edits cannot borrow a newer revision to overwrite another client', async () => {
    const { dataService, server, control } = integration()
    const settings = settingsCategories(dataService)
    await settings.loadResourceCategories()
    server.config.resourceCategories.push({ id: 'b', name: 'B', folder: 'b' })
    server._revisions.config = 'v2'
    await dataService.load()
    settings.newCategory.value = { id: 'c', name: 'C', folder: 'c' }
    await settings.saveCategory()
    assert.equal(control.payloads[0]._revisions.config, 'v1')
    assert.deepEqual(server.config.resourceCategories.map(item => item.id), ['a', 'b'])
    assert.deepEqual(settings.resourceCategories.value.map(item => item.id), ['a'])
    assert.equal(settings.errors.length, 1)
    assert.equal(settings.showCategoryModal.value, true)
  })

  it('settings category saves are serialized and keep unrelated config fields', async () => {
    const { dataService, server, control } = integration()
    const settings = settingsCategories(dataService)
    await settings.loadResourceCategories()
    settings.newCategory.value = { id: 'c', name: 'C', folder: 'c' }
    const first = settings.saveCategory()
    settings.newCategory.value = { id: 'd', name: 'D', folder: 'd' }
    await Promise.all([first, settings.saveCategory()])
    assert.deepEqual(server.config.resourceCategories.map(item => item.id), ['a', 'c', 'd'])
    assert.equal(server.config.preserved, 'value')
    assert.deepEqual(control.payloads.map(item => item._revisions.config), ['v1', 'v1+'])
    assert.equal(settings.errors.length, 0)
  })

  it('settings load failures stay visible and prevent category saves', async () => {
    const { dataService, control } = integration()
    control.failLoad = true
    const settings = settingsCategories(dataService)
    await settings.loadResourceCategories()
    settings.newCategory.value = { name: 'C', folder: 'c' }
    await settings.saveCategory()
    assert.equal(control.payloads.length, 0)
    assert.equal(settings.errors.length, 2)
    assert.equal(settings.resourceCategories.value.length, 0)
    assert.equal(settings.showCategoryModal.value, true)
  })

  it('rapid checklist toggles persist both edits with successive revisions', async () => {
    const { dataService, server, control } = integration()
    const checklist = store('checklist', 'useChecklistStore', dataService)
    await checklist.loadChecklists()
    await Promise.all([checklist.toggleItem('c1', 0), checklist.toggleItem('c1', 1)])
    assert.deepEqual(server.projectChecklists.__global__.startup.cards[0].items.map(item => item.checked), [true, true])
    assert.deepEqual(control.payloads.map(item => item._revisions.projectChecklists), ['v1', 'v1+'])
    assert.equal(checklist.error, null)
  })

  it('checklist save failures reject and restore UI, then retry loads fresh data', async () => {
    const { dataService, server, control } = integration()
    const checklist = store('checklist', 'useChecklistStore', dataService)
    await checklist.loadChecklists()
    control.failSave = true
    await assert.rejects(checklist.addItem('c1', 'Unsaved item'), /save unavailable/)
    assert.equal(checklist.activeChecklist.cards[0].items.length, 2)
    assert.equal(checklist.error, 'save unavailable')
    control.failSave = false
    server.projectChecklists.__global__.startup.cards[0].items.push({ text: 'Remote item', checked: false })
    server._revisions.projectChecklists = 'v2'
    await checklist.addItem('c1', 'Retry item')
    assert.deepEqual(server.projectChecklists.__global__.startup.cards[0].items.map(item => item.text), ['A', 'B', 'Remote item', 'Retry item'])
    assert.equal(control.loads, 2)
  })

  it('checklist cold writes load first and failed loads never write', async () => {
    const good = integration()
    const checklist = store('checklist', 'useChecklistStore', good.dataService)
    await checklist.toggleItem('c1', 0)
    assert.equal(good.control.loads, 1)
    assert.equal(good.server.projectChecklists.__global__.startup.cards[0].items[0].checked, true)
    const bad = integration()
    bad.control.failLoad = true
    const unavailable = store('checklist', 'useChecklistStore', bad.dataService)
    await assert.rejects(unavailable.addItem('c1', 'No write'), /load unavailable/)
    assert.equal(bad.control.payloads.length, 0)
  })

  it('resource store cannot overwrite newer config after another page reloads', async () => {
    const { dataService, server } = integration()
    const resource = store('resource', 'useResourceStore', dataService)
    await resource.load()
    server.config.resourceCategories.push({ id: 'b', name: 'B', folder: 'b' })
    server._revisions.config = 'v2'
    await dataService.load()
    await assert.rejects(resource.addCategory({ name: 'C', folder: 'c' }), /revision conflict/)
    assert.deepEqual(server.config.resourceCategories.map(item => item.id), ['a', 'b'])
    assert.deepEqual(resource.categories.map(item => item.id), ['a'])
  })

  it('project store uses loaded revisions with the production data service', async () => {
    const { dataService, control } = integration()
    const project = store('project', 'useProjectStore', dataService)
    await project.saveProject({ id: 'p1', name: 'First' })
    await project.saveProject({ id: 'p1', name: 'Second' })
    assert.deepEqual(control.payloads.map(item => item._revisions.projects), ['v1', 'v1+'])
    assert.ok(control.payloads.every(item => !Object.hasOwn(item, 'config')))
  })
})
