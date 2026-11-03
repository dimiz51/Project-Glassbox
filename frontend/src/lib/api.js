// Typed API client. Every failure becomes an ApiError carrying an error object of the same
// shape the server uses: { code, message, hint, detail } (see backend/app/core/errors.py).

// Errors only the browser can detect: the server can't report that it's unreachable.
export const CLIENT_ERRORS = {
  backend_unreachable: {
    code: 'backend_unreachable',
    message: "Can't reach the Project Glassbox server.",
    hint: 'Start it with `docker compose up`, then reload this page.',
  },
  connection_lost: {
    code: 'connection_lost',
    message: 'Lost the connection to the server.',
    hint: 'Reload the page. Chats are kept as long as the server keeps running.',
  },
  unexpected: {
    code: 'unexpected',
    message: 'Something went wrong.',
    hint: 'Try again. If it keeps happening, check `docker compose logs backend`.',
  },
}

export class ApiError extends Error {
  constructor(error) {
    super(error.message)
    this.error = error
  }
}

export async function api(path, options = {}) {
  let res
  try {
    res = await fetch(`/api${path}`, options)
  } catch {
    throw new ApiError(CLIENT_ERRORS.backend_unreachable)
  }
  if (res.status === 502 || res.status === 504) throw new ApiError(CLIENT_ERRORS.backend_unreachable) // proxy up, backend down
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(body?.code ? body : { ...CLIENT_ERRORS.unexpected, detail: `HTTP ${res.status}` })
  return body
}

export const toError = (e) => (e instanceof ApiError ? e.error : { ...CLIENT_ERRORS.unexpected, detail: String(e) })
