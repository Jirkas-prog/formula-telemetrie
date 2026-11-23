'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');
const { normalizeRelative, resolveInside } = require('../lib/files');

test('bezpečné relativní cesty projdou', () => {
  assert.equal(normalizeRelative('chapters/uvod.tex'), 'chapters/uvod.tex');
  assert.equal(resolveInside('/workspace', 'images/logo.pdf').target.endsWith(path.join('images', 'logo.pdf')), true);
});

test('únik z projektu a interní cesty jsou odmítnuty', () => {
  assert.throws(() => normalizeRelative('../auth/users.json'));
  assert.throws(() => normalizeRelative('/etc/passwd'));
  assert.throws(() => normalizeRelative('.oleaf-build/main.pdf'));
});
