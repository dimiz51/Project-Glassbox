// The UI state of a session is a pure function of its event log (replayed by the backend on connect).
export function reduce(events) {
  const messages = [] // {role:'user', text} | run
  const shots = [] // [{step, src, url, coordinate, label}] every observe, in order: the session's timeline
  let run = null
  let url = ''
  let point = null // last click/type target [x, y] on the 0-1000 grid

  const stepOf = (n) => run?.items.findLast((i) => i.kind === 'step' && i.n === n)

  for (const ev of events) {
    switch (ev.type) {
      case 'user':
        if (run?.status === 'running') run.items.push({ kind: 'user', text: ev.text }) // steering mid-task
        else messages.push({ role: 'user', text: ev.text })
        break
      case 'start':
        run = { role: 'agent', items: [], answer: null, status: 'running', error: null, steps: 0, seconds: 0 }
        messages.push(run)
        break
      case 'observe': {
        if (!run) break
        // this observe is the "after" of the previous step's browser action
        const prev = run.items.findLast((i) => i.kind === 'step')
        if (prev && prev.label && !prev.talk) prev.after = ev.screenshot
        run.items.push({ kind: 'step', n: ev.step, url: ev.url, shot: ev.screenshot })
        run.steps = ev.step
        shots.push({ step: ev.step, src: ev.screenshot, url: ev.url, coordinate: null, label: null })
        url = ev.url
        break
      }
      case 'action': {
        const s = stepOf(ev.step)
        // message/done aren't browser actions: their text shows as chat text / the answer instead
        if (s) Object.assign(s, { thought: ev.thought, label: ev.label, seconds: ev.seconds, coordinate: ev.coordinate, talk: ev.action === 'message' || ev.action === 'done' })
        if (run) run.seconds += ev.seconds || 0
        const shot = shots.findLast((x) => x.step === ev.step)
        if (shot) Object.assign(shot, { coordinate: ev.coordinate, label: ev.label })
        if (ev.coordinate) point = { at: ev.coordinate, step: ev.step }
        break
      }
      case 'message':
        run?.items.push({ kind: 'message', text: ev.text })
        break
      case 'error': // ev.error = { code, message, hint, detail }
        if (ev.fatal && run) {
          run.status = 'error'
          run.error = ev.error
        } else {
          const s = stepOf(ev.step)
          if (s) s.error = ev.error
        }
        break
      case 'answer':
        if (!run) break
        run.answer = ev.text
        run.status = 'done'
        break
      case 'stopped':
        if (run) run.status = 'stopped'
        break
    }
  }
  return { messages, shots, url, point, running: run?.status === 'running' }
}
