import fs from 'node:fs'
import assert from 'node:assert/strict'

const source = name => fs.readFileSync(new URL(`../../src/views/${name}DetailView.vue`, import.meta.url), 'utf8')

function operation(view, name, env) {
  const script = source(view).match(new RegExp(`const ${name} = async [\\s\\S]*?\\n}`))[0]
  return new Function(...Object.keys(env), `${script}\nreturn ${name};`)(...Object.values(env))
}

describe('Material file identity in detail actions', () => {
  for (const [view, entityKey, identityKey, type, hasDownload] of [
    ['Player', 'player', 'playerName', '作品集', true],
    ['Project', 'project', 'projectName', '现场照片', true],
    ['Organization', 'org', 'orgName', '结算', false]
  ]) {
    it(`${view} sends the exact material type with its file name`, async () => {
      const material = { name: '相同 & 文件.pdf', type }
      const requests = []
      const errors = []
      const env = {
        [entityKey]: { value: { name: '主体 & 名称', materials: [material] } },
        getBlob: async url => { requests.push({ download: url }); return new Uint8Array() },
        fetchWithAuth: async (url, options) => {
          requests.push({ url, payload: JSON.parse(options.body) })
          return { json: async () => ({ success: true }) }
        },
        URL: { createObjectURL: () => 'blob:fixture', revokeObjectURL() {} },
        document: { createElement: () => ({ click() {} }), body: { appendChild() {}, removeChild() {} } },
        confirm: async () => true, success() {}, error: message => errors.push(message),
        console: { error() {} },
        playerStore: { loadPlayers: async () => {} }, loadPlayerMaterials: async () => {},
        loadProjectMaterials: async () => {}, loadOrgMaterials: async () => {}
      }
      if (hasDownload) {
        await operation(view, 'downloadMaterial', env)(material)
        const query = new URL(requests[0].download, 'http://fixture').searchParams
        assert.equal(query.get(identityKey), '主体 & 名称')
        assert.equal(query.get('fileName'), material.name)
        assert.equal(query.get('materialType'), type)
      }
      await operation(view, 'deleteMaterial', env)(view === 'Player' ? material : 0)
      const { payload } = requests.at(-1)
      assert.equal(payload[identityKey], '主体 & 名称')
      assert.equal(payload.fileName, material.name)
      assert.equal(payload.materialType, type)
      assert.deepEqual(errors, [])
    })
  }
})
