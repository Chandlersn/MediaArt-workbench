import fs from 'node:fs'
import nodeAssert from 'node:assert/strict'

function createService(get, post) {
  const source = fs.readFileSync(new URL('../../src/services/dataService.js', import.meta.url), 'utf8')
    .replace(/^import .*$/gm, '').replace(/export /g, '')
  return new Function('get', 'post', `${source}; return {load, getData, getRevision, setData, save, isLoaded}`)(get, post)
}

const snapshot = () => ({ projects: [{ id: 'p1', name: 'Original' }],
  organizations: [{ id: 'o1', name: 'Original org' }], users: [{ id: 'u1' }],
  _revisions: { projects: 'p-v1', organizations: 'o-v1', users: 'u-v1' } })

describe('数据保存与冲突保护', () => {
  it('尚未加载不能通过 setData 伪造已加载状态', async () => {
    let calls = 0
    const service = createService(async () => { throw new Error('offline') }, async () => { calls++ })
    nodeAssert.throws(() => service.setData('projects', []))
    await nodeAssert.rejects(service.load())
    await nodeAssert.rejects(service.save())
    nodeAssert.equal(service.isLoaded(), false)
    nodeAssert.equal(calls, 0)
  })

  it('只提交修改段，保留加载版本，不携带用户和其他旧数据', async () => {
    let body
    const service = createService(async () => ({ success: true, data: snapshot() }), async (_, payload) => {
      body = payload
      return { success: true, _revisions: { projects: 'p-v2' } }
    })
    await service.load()
    service.setData('projects', [{ id: 'p1', name: 'Edited' }], service.getRevision('projects'))
    await service.save()
    nodeAssert.deepEqual(Object.keys(body).sort(), ['_revisions', '_snapshot', 'projects'])
    nodeAssert.equal(body._revisions.projects, 'p-v1')
    nodeAssert.equal(service.getRevision('projects'), 'p-v2')
    nodeAssert.equal(service.getRevision('organizations'), 'o-v1')
    nodeAssert.equal(service.getData('projects')[0].name, 'Edited')
  })

  it('其他页面刷新快照后仍提交调用方原先保存的版本', async () => {
    let server = snapshot()
    let sent
    const service = createService(async () => ({ data: structuredClone(server) }), async (_, body) => {
      sent = body
      throw new Error('409 conflict')
    })
    await service.load()
    const loadedRevision = service.getRevision('projects')
    server._revisions.projects = 'other-window-version'
    await service.load()
    service.setData('projects', [{ id: 'p1', name: 'Stale edit' }], loadedRevision)
    await nodeAssert.rejects(service.save(), /conflict/)
    nodeAssert.equal(sent._revisions.projects, 'p-v1')
  })

  it('排队保存冻结载荷，不被后续对象修改污染', async () => {
    const bodies = []
    const service = createService(async () => ({ data: snapshot() }), async (_, body) => {
      bodies.push(structuredClone(body))
      return { success: true, _revisions: { projects: 'p-v2', organizations: 'o-v2' } }
    })
    await service.load()
    const projects = [{ id: 'p1', name: 'First edit' }]
    service.setData('projects', projects)
    const first = service.save()
    projects[0].name = 'Unsaved edit'
    service.setData('organizations', [{ id: 'o1', name: 'Org edit' }])
    await Promise.all([first, service.save()])
    nodeAssert.equal(bodies[0].projects[0].name, 'First edit')
    nodeAssert.equal(bodies[1].projects, undefined)
  })

  it('失败的修改不会夹带到下一次无关保存中', async () => {
    const bodies = []
    const service = createService(async () => ({ data: snapshot() }), async (_, body) => {
      bodies.push(body)
      if (body.projects) throw new Error('conflict')
      return { success: true, _revisions: { organizations: 'o-v2' } }
    })
    await service.load()
    service.setData('projects', [])
    await nodeAssert.rejects(service.save())
    service.setData('organizations', [])
    await service.save()
    nodeAssert.equal(bodies[1].projects, undefined)
    nodeAssert.equal(service.getData('projects')[0].name, 'Original')
    nodeAssert.equal(service.getRevision('projects'), 'p-v1')
  })

  it('读取的副本与待提交修改都不会污染已保存缓存', async () => {
    const service = createService(async () => ({ data: snapshot() }), async () => {
      throw new Error('offline')
    })
    const loaded = await service.load()
    loaded.projects[0].name = 'Mutated load result'
    const edited = service.getData('projects')
    edited[0].name = 'Unsaved'
    service.setData('projects', edited)
    nodeAssert.equal(service.getData('projects')[0].name, 'Original')
    await nodeAssert.rejects(service.save(), /offline/)
    nodeAssert.equal(service.getData('projects')[0].name, 'Original')
  })

  it('加载在途时排队保存，成功后的缓存值与版本一致', async () => {
    let finishLoad
    let holdLoad = false
    const service = createService(async () => {
      if (holdLoad) await new Promise(resolve => { finishLoad = resolve })
      return { data: snapshot() }
    }, async () => ({ success: true, _revisions: { projects: 'p-v2' } }))
    await service.load()
    holdLoad = true
    const loading = service.load()
    await Promise.resolve()
    service.setData('projects', [{ id: 'p1', name: 'Edited during load' }], 'p-v1')
    const saving = service.save()
    finishLoad()
    await Promise.all([loading, saving])
    nodeAssert.equal(service.getData('projects')[0].name, 'Edited during load')
    nodeAssert.equal(service.getRevision('projects'), 'p-v2')
  })
})
