import fs from 'node:fs'
import assert from 'node:assert/strict'
import { ref, computed } from 'vue'
import { defineStore, createPinia, setActivePinia } from 'pinia'

const clone = value => JSON.parse(JSON.stringify(value))
const source = path => fs.readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8')
  .replace(/^import .*$/mg, '').replace(/^export /mg, '')
const quietConsole = { error() {}, warn() {} }

function workflow(initial = {}, storageOverride) {
  const server = {
    certificates: [],
    certSettings: {
      activeSessionId: 's1', sessionMeta: {},
      templates: { province: 'P{seq:4}', national: 'Q{seq}' }
    },
    _revisions: { certificates: 'c1', certSettings: 's1' },
    ...clone(initial)
  }
  const calls = { writes: [], failSave: false }
  const get = async () => ({ success: true, data: clone(server) })
  const post = async (_, payload) => {
    calls.writes.push(clone(payload))
    if (calls.failSave) throw new Error('write denied')
    for (const key of Object.keys(payload._revisions)) {
      if (server._revisions[key] !== payload._revisions[key]) throw new Error('revision conflict')
    }
    for (const key of Object.keys(payload._revisions)) {
      server[key] = clone(payload[key])
      server._revisions[key] += '+'
    }
    return { success: true, _revisions: clone(server._revisions) }
  }
  const dataService = new Function('get', 'post', `${source('src/services/dataService.js')}
    return {load,getData,getRevision,setData,save};`)(get, post)
  const preferences = new Map()
  const storage = storageOverride || {
    getItem: key => preferences.get(key) ?? null,
    setItem: (key, value) => preferences.set(key, value),
    removeItem: key => preferences.delete(key)
  }
  const makeStore = () => {
    setActivePinia(createPinia())
    return new Function('defineStore', 'ref', 'computed', 'dataService', 'useAuditLogStore', 'sessionStorage', 'console',
      `${source('src/stores/certificate.js')}\nreturn useCertificateStore();`)(
      defineStore, ref, computed, dataService, () => ({ addLog: async () => {} }), storage, quietConsole)
  }
  return { store: makeStore(), makeStore, server, calls, preferences }
}

const previousCertificate = {
  certNumber: 'P0001', sessionId: 's1', playerId: 'a', playerName: 'Original',
  certRound: 'province', projectId: 'project-a', award: 'Gold', workName: 'Manual title'
}
const otherCertificate = { certNumber: 'P0002', sessionId: 's2', playerId: 'other', certRound: 'province' }
const syncOptions = { assignNumbers: true, certRound: 'province' }

describe('Certificate workflow', () => {
  it('first synchronization creates a visible batch and inherits each player project', async () => {
    const { store, server } = workflow()
    const result = await store.syncFromPlayers([
      { id: 'a', name: 'A', projectId: 'project-a' },
      { id: 'b', name: 'B', projectId: 'project-b' }
    ], [], syncOptions)
    assert.deepEqual(result, { created: 2, updated: 0, skipped: 0 })
    assert.equal(store.sessions.length, 1)
    assert.equal(store.visibleCertificates.length, 2)
    assert.deepEqual(server.certificates.map(item => item.projectId), ['project-a', 'project-b'])
    assert.equal(store.activeSessionId, server.certificates[0].sessionId)
  })

  it('repeated synchronization updates the original batch without an empty new batch', async () => {
    const { store, server, calls } = workflow({ certificates: [previousCertificate] })
    const result = await store.syncFromPlayers([{ id: 'a', name: 'Updated', projectId: 'project-a' }], [], syncOptions)
    assert.deepEqual(result, { created: 0, updated: 1, skipped: 0 })
    assert.equal(store.activeSessionId, 's1')
    assert.equal(store.visibleCertificates.length, 1)
    assert.equal(store.sessions.length, 1)
    assert.equal(store.visibleCertificates[0].playerName, 'Updated')
    assert.equal(store.visibleCertificates[0].award, 'Gold')
    assert.equal(store.visibleCertificates[0].workName, 'Manual title')
    assert.deepEqual(server.certSettings.sessionMeta, {})
    assert.deepEqual(Object.keys(calls.writes[0]._revisions), ['certificates'])
  })

  it('updating a different batch selects a real updated batch', async () => {
    const { store } = workflow({ certificates: [previousCertificate, otherCertificate] })
    await store.loadCertificates()
    await store.switchSession('s2')
    await store.syncFromPlayers([{ id: 'a', name: 'Updated' }], [], syncOptions)
    assert.equal(store.activeSessionId, 's1')
    assert.equal(store.visibleCertificates[0].playerName, 'Updated')
    assert.equal(store.sessions.length, 2)
  })

  it('mixed synchronization creates a batch only for new certificates', async () => {
    const { store, server } = workflow({ certificates: [previousCertificate] })
    const result = await store.syncFromPlayers([{ id: 'a', name: 'Updated' }, { id: 'b', name: 'New' }], [], syncOptions)
    assert.deepEqual(result, { created: 1, updated: 1, skipped: 0 })
    assert.equal(store.visibleCertificates.length, 1)
    assert.equal(store.visibleCertificates[0].playerId, 'b')
    assert.equal(server.certificates.find(item => item.playerId === 'a').sessionId, 's1')
    assert.equal(server.certificates.find(item => item.playerId === 'a').award, 'Gold')
    assert.equal(store.sessions.length, 2)
  })

  it('a project with no matching players performs no write and leaves the current batch intact', async () => {
    const { store, calls } = workflow({ certificates: [previousCertificate] })
    await store.loadCertificates()
    const result = await store.syncFromPlayers([{ id: 'b', name: 'B', projectId: 'another' }], [], { ...syncOptions, projectId: 'missing' })
    assert.deepEqual(result, { created: 0, updated: 0, skipped: 0 })
    assert.equal(store.activeSessionId, 's1')
    assert.equal(calls.writes.length, 0)
    assert.equal(store.sessions.length, 1)
  })

  it('viewer switching and reloads need no writes and retain the local selection', async () => {
    const { store, makeStore, calls, server } = workflow({ certificates: [previousCertificate, otherCertificate] })
    calls.failSave = true
    await store.loadCertificates()
    await store.switchSession('s2')
    await store.loadCertificates()
    assert.equal(store.activeSessionId, 's2')
    assert.equal(store.visibleCertificates[0].certNumber, 'P0002')
    const reloaded = makeStore()
    await reloaded.loadCertificates()
    assert.equal(reloaded.activeSessionId, 's2')
    assert.equal(server.certSettings.activeSessionId, 's1')
    assert.equal(calls.writes.length, 0)
  })

  it('an externally removed selected batch falls back to an existing batch', async () => {
    const { store, makeStore, server, calls } = workflow({ certificates: [previousCertificate, otherCertificate] })
    await store.loadCertificates()
    await store.switchSession('s2')
    server.certificates = [clone(previousCertificate)]
    await store.loadCertificates()
    assert.equal(store.activeSessionId, 's1')
    assert.equal(store.visibleCertificates.length, 1)
    const reloaded = makeStore()
    await reloaded.loadCertificates()
    assert.equal(reloaded.activeSessionId, 's1')
    assert.equal(calls.writes.length, 0)
  })

  it('unavailable browser storage does not prevent switching batches', async () => {
    const deniedStorage = { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') }, removeItem() { throw new Error('denied') } }
    const { store, calls } = workflow({ certificates: [previousCertificate, otherCertificate] }, deniedStorage)
    await store.loadCertificates()
    await store.switchSession('s2')
    assert.equal(store.activeSessionId, 's2')
    assert.equal(calls.writes.length, 0)
  })

  it('deleting the last certificate in the selected batch selects a remaining batch', async () => {
    const { store } = workflow({ certificates: [previousCertificate, otherCertificate] })
    await store.loadCertificates()
    await store.switchSession('s2')
    await store.deleteCert('P0002', 's2')
    assert.equal(store.activeSessionId, 's1')
    assert.equal(store.visibleCertificates.length, 1)
  })

  it('invalid batch selections and empty imports do not create empty sessions', async () => {
    const { store, calls, server } = workflow({ certificates: [previousCertificate] })
    await store.loadCertificates()
    await assert.rejects(store.switchSession('missing'))
    await assert.rejects(store.importCertificates([{ playerName: 'No certificate number' }]))
    assert.equal(store.activeSessionId, 's1')
    assert.deepEqual(server.certSettings.sessionMeta, {})
    assert.equal(calls.writes.length, 0)
  })

  it('failed synchronization restores the selected batch without changing the browser preference', async () => {
    const { store, calls, makeStore } = workflow({ certificates: [previousCertificate, otherCertificate] })
    await store.loadCertificates()
    await store.switchSession('s2')
    calls.failSave = true
    await assert.rejects(store.syncFromPlayers([{ id: 'a', name: 'Updated' }], [], syncOptions), /write denied/)
    assert.equal(store.activeSessionId, 's2')
    assert.equal(store.certificates[0].playerName, 'Original')
    const reloaded = makeStore()
    await reloaded.loadCertificates()
    assert.equal(reloaded.activeSessionId, 's2')
  })
})
