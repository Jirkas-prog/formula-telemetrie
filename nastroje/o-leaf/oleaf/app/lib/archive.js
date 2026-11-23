'use strict';

const AdmZip = require('adm-zip');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { ensureDir } = require('./files');

function sanitizedEntryName(name) {
  const clean = name.replaceAll('\\', '/').replace(/^\.\//, '');
  if (!clean || clean === '.') return '';
  if (clean.startsWith('/') || /^[A-Za-z]:/.test(clean)) throw new Error('ZIP obsahuje absolutní cestu.');
  const parts = clean.split('/').filter(Boolean);
  if (parts.some((part) => part === '.' || part === '..')) throw new Error('ZIP se pokouší zapisovat mimo cílovou složku.');
  return parts.join('/');
}

function stripCommonRoot(names) {
  const split = names.map((name) => name.split('/'));
  if (!split.length || split.some((parts) => parts.length < 2)) return names;
  const root = split[0][0];
  return split.every((parts) => parts[0] === root) ? split.map((parts) => parts.slice(1).join('/')) : names;
}

async function extractZip(buffer, destination, maxExpandedBytes) {
  const archive = new AdmZip(buffer);
  const entries = archive.getEntries();
  if (!entries.length) throw new Error('ZIP je prázdný.');
  const records = entries
    .map((entry) => ({ entry, name: sanitizedEntryName(entry.entryName) }))
    .filter((record) => record.name);
  if (!records.length) throw new Error('ZIP neobsahuje žádné soubory.');
  const outputNames = stripCommonRoot(records.map((record) => record.name));
  let expanded = 0;
  await ensureDir(destination);

  for (let index = 0; index < records.length; index += 1) {
    const entry = records[index].entry;
    const relative = outputNames[index];
    if (!relative) continue;
    const unixType = (entry.header.attr >>> 16) & 0xf000;
    if (unixType === 0xa000) throw new Error('ZIP obsahuje symbolický odkaz.');
    const target = path.resolve(destination, relative);
    const root = path.resolve(destination);
    if (!target.startsWith(`${root}${path.sep}`) && target !== root) throw new Error('Neplatný cíl v ZIPu.');
    if (entry.isDirectory) {
      await ensureDir(target);
      continue;
    }
    expanded += entry.header.size;
    if (expanded > maxExpandedBytes) throw new Error('Rozbalený ZIP překračuje povolenou velikost.');
    await ensureDir(path.dirname(target));
    await fsp.writeFile(target, entry.getData(), { mode: 0o600 });
  }
}

async function projectZip(projectRoot) {
  const archive = new AdmZip();
  const visit = async (directory, prefix = '') => {
    for (const item of await fsp.readdir(directory, { withFileTypes: true })) {
      if (item.name === '.git' || item.name.startsWith('.oleaf-') || item.isSymbolicLink()) continue;
      const relative = prefix + item.name;
      const full = path.join(directory, item.name);
      if (item.isDirectory()) await visit(full, `${relative}/`);
      else if (item.isFile()) archive.addFile(relative, await fsp.readFile(full));
    }
  };
  await visit(projectRoot);
  return archive.toBuffer();
}

module.exports = { extractZip, projectZip };
