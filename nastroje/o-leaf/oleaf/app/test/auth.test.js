'use strict';

const assert = require('node:assert/strict');
const os = require('node:os');
const path = require('node:path');
const fsp = require('node:fs/promises');
const test = require('node:test');
const { AuthStore, hashPassword, verifyPassword } = require('../lib/auth');

test('heslo je ověřitelné, ale není uloženo čitelně', () => {
  const encoded = hashPassword('spravne-heslo');
  assert.equal(encoded.includes('spravne-heslo'), false);
  assert.equal(verifyPassword('spravne-heslo', encoded), true);
  assert.equal(verifyPassword('spatne-heslo', encoded), false);
});

test('účty dostávají různá kompilační UID a relace', async () => {
  const temporary = await fsp.mkdtemp(path.join(os.tmpdir(), 'oleaf-auth-'));
  try {
    const auth = new AuthStore(path.join(temporary, 'auth'));
    await auth.init();
    const alice = await auth.register('alice', 'dlouhe-heslo-alice');
    const bob = await auth.register('bob', 'dlouhe-heslo-bob');
    assert.notEqual(alice.compileUid, bob.compileUid);
    const login = await auth.login('alice', 'dlouhe-heslo-alice');
    assert.equal((await auth.session(login.token)).username, 'alice');
    await auth.logout(login.token);
    assert.equal(await auth.session(login.token), null);
  } finally {
    await fsp.rm(temporary, { recursive: true, force: true });
  }
});

