'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { firstForwardRecord, firstReverseRecord, parseSyncTex, projectRelativeInput } = require('../lib/synctex');

test('parses SyncTeX forward coordinates', () => {
  const output = `SyncTeX result begin
Output:/project/.oleaf-build/main.pdf
Page:3
x:144.250
y:288.500
h:140.000
v:280.000
W:210.000
H:12.000
SyncTeX result end`;
  assert.equal(parseSyncTex(output).length, 1);
  assert.deepEqual(firstForwardRecord(output), {
    page: 3, x: 144.25, y: 288.5, width: 210, height: 12,
  });
});

test('parses reverse result and keeps source inside project', () => {
  const root = path.resolve('test-project');
  const source = path.join(root, 'chapters', 'intro.tex');
  const output = `SyncTeX result begin
Output:main.pdf
Input:${source}
Line:42
Column:-1
Offset:0
SyncTeX result end`;
  assert.deepEqual(firstReverseRecord(output, root), { path: 'chapters/intro.tex', line: 42, column: 0 });
  assert.equal(projectRelativeInput(root, './main.tex'), 'main.tex');
});

test('rejects SyncTeX source paths outside the open project', () => {
  const root = path.resolve('test-project');
  assert.throws(() => projectRelativeInput(root, path.resolve('outside.tex')), /mimo otevřený projekt/);
  assert.throws(() => firstForwardRecord('SyncTeX result begin\nSyncTeX result end'), /nebyla v PDF nalezena/);
});
