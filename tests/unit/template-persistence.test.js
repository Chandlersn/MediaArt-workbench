import fs from 'node:fs'
import assert from 'node:assert/strict'
import { ref } from 'vue'

const clone = value => JSON.parse(JSON.stringify(value))
const source = fs.readFileSync(new URL('../../src/views/TemplatesView.vue', import.meta.url), 'utf8')
const pick = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)))

function editorFixture() {
  const original = [
    { id: 'a', name: 'Template A', background: 'a.png', fields: [{ column: 'name' }] },
    { id: 'b', name: 'Template B', background: 'b.png', fields: [{ column: 'name' }] }
  ]
  const server = { rows: clone(original), revision: 'v1' }
  const control = { fail: false, writes: [], loads: 0 }
  let pending
  const env = {
    templates: ref([]), editor: ref(null), previewRecord: ref(null), savingTpl: ref(false),
    errors: [], successes: [], confirm: async () => true,
    warning: () => {},
    dataService: {
      async load() { control.loads++ },
      getData(key) { return key === 'printTemplates' ? clone(server.rows) : [] },
      getRevision() { return server.revision },
      setData(key, rows, revision) { pending = { rows: clone(rows), revision } },
      async save() {
        control.writes.push(clone(pending))
        if (control.fail) throw new Error('save unavailable')
        assert.equal(pending.revision, server.revision)
        server.rows = clone(pending.rows)
        server.revision += '+'
        return { _revisions: { printTemplates: server.revision } }
      }
    }
  }
  env.toastError = message => env.errors.push(message)
  env.success = message => env.successes.push(message)
  const functions = [
    pick('let templatesRevision =', 'onMounted('),
    pick('const removeTpl =', 'const onBgChange ='),
    pick('const saveTpl =', '// ---- 字体 ----')
  ].join('\n')
  const actions = new Function(...Object.keys(env), `${functions}\nreturn {loadTemplates,removeTpl,saveTpl};`)(...Object.values(env))
  return { ...env, ...actions, control, server, original }
}

describe('Print template persistence', () => {
  it('failed deletion retains the row and displays the failure', async () => {
    const view = editorFixture()
    await view.loadTemplates()
    view.control.fail = true
    await view.removeTpl(view.templates.value[0])
    assert.deepEqual(view.templates.value, view.original)
    assert.equal(view.errors.length, 1)
    assert.equal(view.successes.length, 0)
  })

  it('failed edits retain saved rows and keep the editor open for retry', async () => {
    const view = editorFixture()
    await view.loadTemplates()
    view.editor.value = { ...clone(view.original[0]), name: 'Edited' }
    view.control.fail = true
    await view.saveTpl()
    assert.deepEqual(view.templates.value, view.original)
    assert.equal(view.editor.value.name, 'Edited')
    assert.equal(view.errors.length, 1)
    view.control.fail = false
    await view.saveTpl()
    assert.equal(view.server.rows[0].name, 'Edited')
    assert.equal(view.editor.value, null)
  })

  it('rapid deletions derive each candidate from the last committed list', async () => {
    const view = editorFixture()
    await view.loadTemplates()
    await Promise.all(view.original.map(row => view.removeTpl(row)))
    assert.deepEqual(view.server.rows, [])
    assert.deepEqual(view.control.writes.map(item => item.revision), ['v1', 'v1+'])
    assert.deepEqual(view.templates.value, [])
    assert.equal(view.errors.length, 0)
  })

  it('reactivation during editing keeps the original version until edits are resolved', async () => {
    const view = editorFixture()
    await view.loadTemplates()
    view.editor.value = clone(view.original[0])
    await view.loadTemplates()
    assert.equal(view.control.loads, 1)
  })
})
