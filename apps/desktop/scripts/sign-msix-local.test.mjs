import assert from 'node:assert/strict'
import { test } from 'vitest'

import { localSignFile, localSigningConfigured } from './sign-msix.mjs'

test('local signing is on only with a thumbprint and without Azure', () => {
  assert.equal(localSigningConfigured({}), false)
  assert.equal(localSigningConfigured({ HERMES_WIN_CERT_THUMBPRINT: 'AB' }), true)
  assert.equal(
    localSigningConfigured({ HERMES_WIN_CERT_THUMBPRINT: 'AB', AZURE_SIGN_ENDPOINT: 'e', AZURE_CLIENT_ID: 'c' }),
    false
  )
})

test('localSignFile runs signtool with the thumbprint and a timestamp', () => {
  /** @type {Array<[string, string[]]>} */
  const calls = []
  localSignFile('a.msix', { HERMES_WIN_CERT_THUMBPRINT: 'AB12', HERMES_WIN_SIGNTOOL: 'st.exe' }, (c, a) => calls.push([c, a]))
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], 'st.exe')
  assert.deepEqual(calls[0][1].slice(0, 4), ['sign', '/fd', 'sha256', '/sha1'])
  assert.ok(calls[0][1].includes('AB12'))
  assert.ok(calls[0][1].includes('/tr'))
  assert.equal(calls[0][1].at(-1), 'a.msix')
})
