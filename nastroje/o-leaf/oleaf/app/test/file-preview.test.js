'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { hexPreview, isUtf8Text, kindFor, mimeFor } = require('../lib/file-preview');

test('UTF-8 soubory se rozpoznají jako editovatelný text', () => {
  const content = Buffer.from('Příliš žluťoučký kůň\n\\section{Test}', 'utf8');
  assert.equal(isUtf8Text(content), true);
  assert.equal(kindFor('kapitola.tex', content, true), 'text');
  assert.equal(kindFor('README', content, true), 'text');
});

test('PDF a média se otevřou ve správném typu náhledu', () => {
  assert.equal(kindFor('vysledek.pdf', Buffer.from('%PDF-1.7'), true), 'pdf');
  assert.equal(kindFor('foto.PNG', Buffer.from([0x89, 0x50]), false), 'image');
  assert.equal(kindFor('schema.svg', Buffer.from('<svg/>'), true), 'image');
  assert.equal(kindFor('zaznam.mp4', Buffer.alloc(0), false), 'video');
  assert.equal(kindFor('zvuk.flac', Buffer.alloc(0), false), 'audio');
});

test('binární a neúplné velké soubory nejsou nabídnuty k textové editaci', () => {
  assert.equal(kindFor('data.bin', Buffer.from([0, 1, 2, 3]), true), 'binary');
  assert.equal(kindFor('obri-log.txt', Buffer.from('jen začátek'), false), 'binary');
});

test('MIME typ a hex náhled jsou stabilní', () => {
  assert.equal(mimeFor('document.pdf'), 'application/pdf');
  assert.equal(mimeFor('soubor.xyz'), 'application/octet-stream');
  assert.equal(hexPreview(Buffer.from([0x41, 0x00, 0xff])), '00000000  41 00 ff                                         A··');
});
