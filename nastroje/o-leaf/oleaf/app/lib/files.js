'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');

async function ensureDir(dir, mode = 0o700) {
  await fsp.mkdir(dir, { recursive: true, mode });
  await fsp.chmod(dir, mode).catch(() => {});
}

async function atomicWrite(file, value, mode = 0o600) {
  await ensureDir(path.dirname(file));
  const temporary = `${file}.${process.pid}.${crypto.randomBytes(5).toString('hex')}.tmp`;
  await fsp.writeFile(temporary, value, { mode });
  await fsp.rename(temporary, file);
  await fsp.chmod(file, mode).catch(() => {});
}

async function readJson(file, fallback) {
  try {
    return JSON.parse(await fsp.readFile(file, 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT') return fallback;
    throw error;
  }
}

async function writeJson(file, data) {
  await atomicWrite(file, `${JSON.stringify(data, null, 2)}\n`);
}

function normalizeRelative(input) {
  if (typeof input !== 'string' || input.includes('\0')) throw new Error('Neplatná cesta.');
  const portable = input.replaceAll('\\', '/').replace(/^\.\//, '');
  if (!portable || portable.startsWith('/') || /^[A-Za-z]:/.test(portable)) {
    throw new Error('Je vyžadována relativní cesta.');
  }
  const parts = portable.split('/');
  if (parts.some((part) => !part || part === '.' || part === '..')) {
    throw new Error('Cesta obsahuje nepovolenou část.');
  }
  if (parts[0] === '.oleaf-build' || parts[0] === '.oleaf-project.json') {
    throw new Error('Tato interní cesta není přístupná.');
  }
  return parts.join('/');
}

function resolveInside(root, relative) {
  const clean = normalizeRelative(relative);
  const resolvedRoot = path.resolve(root);
  const target = path.resolve(resolvedRoot, clean);
  if (target !== resolvedRoot && !target.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw new Error('Cesta opouští pracovní prostor.');
  }
  let component = resolvedRoot;
  for (const part of clean.split('/')) {
    component = path.join(component, part);
    try {
      if (fs.lstatSync(component).isSymbolicLink()) throw new Error('Symbolické odkazy nejsou povoleny.');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  return { clean, target };
}

function validIdentifier(value) {
  return typeof value === 'string' && /^[a-z0-9][a-z0-9._-]{0,63}$/i.test(value);
}

async function setOwnershipRecursive(target, uid, gid = uid) {
  const stat = await fsp.lstat(target);
  if (stat.isSymbolicLink()) throw new Error('Symbolické odkazy nejsou povoleny.');
  await fsp.chown(target, uid, gid).catch((error) => {
    if (error.code !== 'EPERM') throw error;
  });
  await fsp.chmod(target, stat.isDirectory() ? 0o700 : 0o600).catch(() => {});
  if (!stat.isDirectory()) return;
  const entries = await fsp.readdir(target, { withFileTypes: true });
  for (const entry of entries) {
    await setOwnershipRecursive(path.join(target, entry.name), uid, gid);
  }
}

async function copyTree(source, destination, { overwrite = false } = {}) {
  const stat = await fsp.lstat(source);
  if (stat.isSymbolicLink()) throw new Error('Plugin obsahuje nepovolený symbolický odkaz.');
  if (stat.isDirectory()) {
    await ensureDir(destination);
    for (const entry of await fsp.readdir(source)) {
      await copyTree(path.join(source, entry), path.join(destination, entry), { overwrite });
    }
    return;
  }
  if (!overwrite && fs.existsSync(destination)) return;
  await ensureDir(path.dirname(destination));
  await fsp.copyFile(source, destination);
}

async function projectTree(root, current = '') {
  const base = current ? path.join(root, current) : root;
  const entries = await fsp.readdir(base, { withFileTypes: true });
  const result = [];
  for (const entry of entries.sort((a, b) => {
    if (a.isDirectory() !== b.isDirectory()) return a.isDirectory() ? -1 : 1;
    return a.name.localeCompare(b.name, 'cs');
  })) {
    if (entry.name === '.git' || entry.name.startsWith('.oleaf-')) continue;
    if (entry.isSymbolicLink()) continue;
    const relative = current ? `${current}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      result.push({ name: entry.name, path: relative, type: 'directory', children: await projectTree(root, relative) });
    } else if (entry.isFile()) {
      result.push({ name: entry.name, path: relative, type: 'file' });
    }
  }
  return result;
}

module.exports = {
  atomicWrite,
  copyTree,
  ensureDir,
  normalizeRelative,
  projectTree,
  readJson,
  resolveInside,
  setOwnershipRecursive,
  validIdentifier,
  writeJson,
};

