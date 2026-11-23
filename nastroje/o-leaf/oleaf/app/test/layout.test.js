'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { resolveLayout, dividerAction, clampRatio, fitRatio } = require('../public/assets/layout');

test('desktop defaults to split, phone to editor with closed navigation', () => {
  assert.deepEqual(resolveLayout(null, false), { ratio: .5, mode: 'split', sidebar: true });
  assert.deepEqual(resolveLayout(null, true), { ratio: .5, mode: 'editor', sidebar: false });
});
test('saved layout restores ratio, mode and sidebar, rejects invalid values', () => {
  assert.deepEqual(resolveLayout({ ratio: .66, mode: 'pdf', sidebar: false }, false), { ratio: .66, mode: 'pdf', sidebar: false });
  assert.deepEqual(resolveLayout({ ratio: 'invalid', mode: 'invalid', sidebar: 'yes' }, true), { ratio: .5, mode: 'editor', sidebar: false });
  assert.equal(clampRatio(-10), .12);
  assert.equal(clampRatio(12), .88);
});
test('divider arrows restore split or switch directly to opposite edge', () => {
  for (const [mode, side, expected] of [
    ['split', 'left', 'pdf'], ['split', 'right', 'editor'],
    ['pdf', 'left', 'split'], ['pdf', 'right', 'editor'],
    ['editor', 'left', 'pdf'], ['editor', 'right', 'split'],
  ]) assert.equal(dividerAction(mode, side), expected);
});
test('narrow split keeps controls inside panes without altering saved ratio', () => {
  for (const width of [280, 294, 364, 744, 1168]) {
    for (const requested of [.12, .33, .5, .66, .88]) {
      const available = width - 32;
      const fitted = fitRatio(requested, width, 32);
      const min = Math.min(128, available / 2);
      assert.ok(fitted * available >= min - .001);
      assert.ok((1 - fitted) * available >= min - .001);
    }
  }
  assert.equal(fitRatio(.66, 1168, 28), .66);
});
