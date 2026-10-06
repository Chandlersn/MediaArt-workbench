import nodeAssert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const runner = fileURLToPath(new URL('../run.js', import.meta.url))

function runFixture(source) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mediaart-runner-test-'))
  try {
    const fixture = path.join(directory, 'fixture.test.mjs')
    fs.writeFileSync(fixture, source, 'utf8')
    const result = spawnSync(process.execPath, [runner, fixture], {
      encoding: 'utf8', timeout: 10000, windowsHide: true
    })
    if (result.error) throw result.error
    return { status: result.status, output: result.stdout + result.stderr }
  } finally {
    // directory comes directly from mkdtemp; no project or user data is removed.
    nodeAssert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()))
    fs.rmSync(directory, { recursive: true, force: true })
  }
}

describe('Test runner subprocess regressions', () => {
  it('reports rejected asynchronous tests as failures', () => {
    const result = runFixture(`
      it('async failure', async () => {
        await new Promise(resolve => setTimeout(resolve, 10))
        throw new Error('ASYNC_FAILURE_MARKER')
      })
    `)
    nodeAssert.notEqual(result.status, 0)
    nodeAssert.match(result.output, /ASYNC_FAILURE_MARKER/)
    nodeAssert.match(result.output, /Total: 1\s+Passed: 0\s+Failed: 1/)
  })

  it('reports module import failures instead of succeeding with zero tests', () => {
    const result = runFixture(`import './missing-fixture-module.mjs'`)
    nodeAssert.notEqual(result.status, 0)
    nodeAssert.match(result.output, /missing-fixture-module/)
    nodeAssert.match(result.output, /Total: 1\s+Passed: 0\s+Failed: 1/)
  })

  it('awaits nested setup and teardown hooks in suite order', () => {
    const result = runFixture(`
      const calls = []
      const later = () => new Promise(resolve => setTimeout(resolve, 5))
      describe('outer', () => {
        beforeEach(async () => { await later(); calls.push('outer before') })
        afterEach(async () => { await later(); calls.push('outer after') })
        describe('inner', () => {
          beforeEach(async () => { await later(); calls.push('inner before') })
          afterEach(async () => { await later(); calls.push('inner after') })
          it('first', async () => {
            await later()
            assertDeepEqual(calls, ['outer before', 'inner before'])
            calls.push('body')
          })
        })
        it('sibling', () => {
          assertDeepEqual(calls, [
            'outer before', 'inner before', 'body',
            'inner after', 'outer after', 'outer before'
          ])
        })
      })
      it('after the suites', () => {
        assertDeepEqual(calls.slice(-2), ['outer before', 'outer after'])
      })
    `)
    nodeAssert.equal(result.status, 0, result.output)
    nodeAssert.match(result.output, /Total: 3\s+Passed: 3\s+Failed: 0/)
  })

  it('runs teardown after failed async setup without running the test body', () => {
    const result = runFixture(`
      describe('setup fails', () => {
        beforeEach(async () => { throw new Error('SETUP_FAILURE_MARKER') })
        afterEach(async () => {
          await Promise.resolve()
          console.log('TEARDOWN_COMPLETED_MARKER')
        })
        it('must not run', () => { console.log('UNEXPECTED_BODY_MARKER') })
      })
    `)
    nodeAssert.notEqual(result.status, 0)
    nodeAssert.match(result.output, /SETUP_FAILURE_MARKER/)
    nodeAssert.match(result.output, /TEARDOWN_COMPLETED_MARKER/)
    nodeAssert.doesNotMatch(result.output, /UNEXPECTED_BODY_MARKER/)
  })
})
