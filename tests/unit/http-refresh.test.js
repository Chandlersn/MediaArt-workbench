import fs from 'node:fs'
import assert from 'node:assert/strict'

const source = fs.readFileSync(new URL('../../src/services/http.js', import.meta.url), 'utf8')
  .replace(/^import .*$/mg, '').replace(/^export /mg, '')
const unauthorized = () => new Response(JSON.stringify({ message: 'expired' }), { status: 401 })

function setup(fetchImpl, refreshImpl) {
  const state = { token: 'expired', refreshes: 0, events: 0, calls: 0 }
  const factory = new Function('getAccessToken', 'clearAuthData', 'refreshToken', 'fetch', 'window', 'CustomEvent',
    `${source}\nreturn {get, post, put, del, getBlob, fetchWithAuth};`)
  const http = factory(() => state.token, () => { state.token = null },
    async () => { state.refreshes++; return refreshImpl(state) },
    async (...args) => { state.calls++; return fetchImpl(state, ...args) },
    { dispatchEvent() { state.events++ } }, class {})
  return { http, state }
}

async function withTimeout(promise) {
  let timer
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('request never settled')), 1000)
    })])
  } finally { clearTimeout(timer) }
}

describe('HTTP token refresh regressions', () => {
  it('all concurrent JSON/raw/blob callers reject when shared refresh fails', async () => {
    let rejectRefresh
    const gate = new Promise((_, reject) => { rejectRefresh = reject })
    const { http, state } = setup(() => unauthorized(), () => gate)
    const completion = Promise.allSettled([http.get('/a'), http.fetchWithAuth('/b'), http.getBlob('/c')])
    await new Promise(resolve => setTimeout(resolve, 30))
    rejectRefresh(new Error('refresh unavailable'))
    const results = await withTimeout(completion)
    assert.deepEqual(results.map(result => result.status), ['rejected', 'rejected', 'rejected'])
    assert.equal(state.refreshes, 1)
    assert.equal(state.events, 1)
    assert.equal(state.calls, 3)
  })

  it('a repeated 401 terminates after one refresh and one retry', async () => {
    const { http, state } = setup(() => unauthorized(), state => { state.token = 'fresh' })
    await assert.rejects(withTimeout(http.get('/a')))
    assert.equal(state.refreshes, 1)
    assert.equal(state.calls, 2)
  })

  it('concurrent requests share refresh success and retry with fresh credentials', async () => {
    const { http, state } = setup((state, url, options) => {
      if (options.headers.Authorization === 'Bearer expired') return unauthorized()
      return new Response(JSON.stringify({ success: true, url }))
    }, async state => {
      await new Promise(resolve => setTimeout(resolve, 20))
      state.token = 'fresh'
    })
    const values = await withTimeout(Promise.all([http.get('/a'), http.post('/b', { value: 1 }), http.getBlob('/c')]))
    assert.equal(values[0].success, true)
    assert.equal(values[1].success, true)
    assert.ok(values[2] instanceof Blob)
    assert.equal(state.refreshes, 1)
    assert.equal(state.calls, 6)
  })

  it('a late old-token 401 uses credentials already refreshed by another request', async () => {
    let releaseLate
    const late = new Promise(resolve => { releaseLate = resolve })
    const { http, state } = setup(async (state, url, options) => {
      if (options.headers.Authorization !== 'Bearer expired') return new Response('{"success":true}')
      if (url === '/late') await late
      return unauthorized()
    }, state => { state.token = 'fresh' })
    const waiting = http.get('/late')
    await http.get('/first')
    releaseLate()
    assert.equal((await withTimeout(waiting)).success, true)
    assert.equal(state.refreshes, 1)
    assert.equal(state.calls, 4)
  })

  it('revoked credentials reject without refreshing', async () => {
    const { http, state } = setup(() => new Response('{"message":"revoked"}', { status: 401 }), () => {})
    await assert.rejects(http.fetchWithAuth('/a'))
    assert.equal(state.refreshes, 0)
    assert.equal(state.calls, 1)
  })
})
