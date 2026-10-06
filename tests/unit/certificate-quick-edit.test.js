import assert from 'node:assert/strict'
import { useCertificateQuickEdit } from '../../src/composables/useCertificateQuickEdit.js'

function fixture() {
  const rows = [
    { certNumber: 'SAME', sessionId: 'other', workName: 'Other batch' },
    { certNumber: 'SAME', sessionId: 'current', workName: '' },
    { certNumber: 'NEXT', sessionId: 'current', workName: '' }
  ]
  const calls = []
  const io = { allowed: true, update: null }
  const editor = useCertificateQuickEdit({ canEdit: () => io.allowed, records: () => rows,
    update: async (number, patch, session) => {
      calls.push({ number, patch, session })
      if (io.update) return io.update()
      const record = rows.find(row => row.certNumber === number && row.sessionId === session)
      Object.assign(record, patch)
      return record
    } })
  return { ...editor, rows, calls, io }
}

describe('Certificate quick correction', () => {
  it('saves only the chosen field and exact session, then advances past rows removed by the missing filter', async () => {
    const view = fixture()
    view.begin(view.rows[1], 'workName', view.rows.slice(1))
    view.draft.value.value = 'New work'
    assert.equal(await view.save(true), true)
    assert.deepEqual(view.calls, [{ number: 'SAME', session: 'current', patch: { workName: 'New work', missingWorkName: 0 } }])
    assert.equal(view.rows[0].workName, 'Other batch')
    assert.equal(view.draft.value.certNumber, 'NEXT')
    view.draft.value.value = 'Second work'
    await view.save(true)
    assert.equal(view.draft.value, null)
  })

  it('retains failures and prevents duplicate saves or cancellation during persistence', async () => {
    const view = fixture()
    view.begin(view.rows[1], 'instructor', view.rows.slice(1))
    view.draft.value.value = 'Keep this teacher'
    let reject
    view.io.update = () => new Promise((_, fail) => { reject = fail })
    const pending = view.save(true)
    await view.save(true)
    view.cancel()
    assert.equal(view.calls.length, 1)
    assert.equal(view.draft.value.value, 'Keep this teacher')
    reject(new Error('Version conflict'))
    assert.equal(await pending, false)
    assert.equal(view.draft.value.certNumber, 'SAME')
    assert.equal(view.draft.value.value, 'Keep this teacher')
    assert.match(view.error.value, /conflict/)
    view.io.update = null
    assert.equal(await view.save(false), true)
    assert.equal(view.rows[1].instructor, 'Keep this teacher')
  })

  it('cancel and unchanged advance do not write; viewers and noneditable fields cannot begin', async () => {
    const view = fixture()
    view.io.allowed = false
    assert.equal(view.begin(view.rows[1], 'workName', view.rows), false)
    view.io.allowed = true
    assert.equal(view.begin(view.rows[1], 'certNumber', view.rows), false)
    view.begin(view.rows[1], 'workName', view.rows.slice(1))
    view.draft.value.value = 'Discard'
    view.cancel()
    assert.equal(view.rows[1].workName, '')
    view.begin(view.rows[1], 'workName', view.rows.slice(1))
    await view.save(true)
    assert.equal(view.draft.value.certNumber, 'NEXT')
    assert.equal(view.calls.length, 0)
  })

  it('a record deleted before saving cannot be reported as saved', async () => {
    const view = fixture()
    view.begin(view.rows[1], 'workName', view.rows.slice(1))
    view.draft.value.value = 'Unsaved'
    view.io.update = async () => null
    assert.equal(await view.save(true), false)
    assert.match(view.error.value, /未保存/)
    assert.equal(view.draft.value.value, 'Unsaved')
  })
})
