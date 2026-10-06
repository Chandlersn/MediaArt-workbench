export default async function teardown() {
  const port = process.env.WORKBENCH_E2E_PORT || 18080
  const url = `http://127.0.0.1:${port}`
  try {
    await fetch(`${url}/__acceptance__/shutdown`, {
      method: 'POST',
      headers: { 'X-Acceptance-Token': process.env.WORKBENCH_E2E_SHUTDOWN_TOKEN },
      signal: AbortSignal.timeout(3000),
    })
    for (let attempt = 0; attempt < 30; attempt++) {
      try { await fetch(`${url}/api/status`, { signal: AbortSignal.timeout(500) }) }
      catch { return }
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  } catch { /* Playwright also owns the fixture child if startup failed. */ }
}
