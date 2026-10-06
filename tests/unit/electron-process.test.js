import nodeAssert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { fileURLToPath } from 'node:url'

const mainPath = fileURLToPath(new URL('../../electron/main.cjs', import.meta.url))
const mainSource = fs.readFileSync(mainPath, 'utf8')

function loadMain(platform = 'win32') {
  const spawns = []
  const events = {}
  const timeouts = []
  const context = vm.createContext({
    require(name) {
      if (name === 'electron') return {
        app: { isPackaged: false, on: (name, callback) => { events[name] = callback } },
        ipcMain: { handle() {} }
      }
      if (name === 'path') return path
      if (name === 'http') return {}
      if (name === 'child_process') return {
        spawn(...args) {
          spawns.push(args)
          return { on() {} }
        }
      }
      throw new Error(`Unexpected dependency: ${name}`)
    },
    process: { platform },
    __dirname: path.dirname(mainPath),
    console: { log() {}, error() {} },
    clearInterval() {},
    setTimeout(callback) { timeouts.push(callback) }
  })
  vm.runInContext(mainSource, context, { filename: mainPath })
  return {
    context, spawns, events, timeouts,
    own(child) {
      context.testChild = child
      vm.runInContext('pythonProcess = testChild', context)
    }
  }
}

describe('Electron Python process ownership', () => {
  it('leaves an externally started server and other Python processes running', () => {
    const { context, spawns, timeouts } = loadMain()
    context.stopPythonServer()
    nodeAssert.equal(spawns.length, 0)
    nodeAssert.equal(timeouts.length, 0)
  })

  it('stops only the owned Windows PID once across repeated quit events', () => {
    const main = loadMain()
    main.own({ pid: 4321, exitCode: null, signalCode: null })
    main.events['before-quit']()
    main.events['will-quit']()
    main.context.stopPythonServer()
    nodeAssert.equal(main.spawns.length, 1)
    const [command, args, options] = main.spawns[0]
    nodeAssert.equal(command, 'taskkill')
    nodeAssert.deepEqual(Array.from(args), ['/pid', '4321', '/f', '/t'])
    nodeAssert.equal(options.windowsHide, true)
    nodeAssert.equal(main.timeouts.length, 0)
  })

  it('never terminates an exited child whose PID could have been reused', () => {
    for (const state of [{ exitCode: 0, signalCode: null }, { exitCode: null, signalCode: 'SIGTERM' }]) {
      const main = loadMain()
      main.own({ pid: 4321, ...state })
      main.context.stopPythonServer()
      nodeAssert.equal(main.spawns.length, 0)
    }
  })

  it('signals only its own child on other platforms', () => {
    const main = loadMain('linux')
    const signals = []
    main.own({ pid: 4321, exitCode: null, signalCode: null, kill: signal => signals.push(signal) })
    main.context.stopPythonServer()
    main.context.stopPythonServer()
    nodeAssert.deepEqual(signals, ['SIGTERM'])
    nodeAssert.equal(main.spawns.length, 0)
  })
})
