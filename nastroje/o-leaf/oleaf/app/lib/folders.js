'use strict';

const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');

function inside(root, target) {
  const relative = path.relative(root, target);
  return !relative || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}

class FolderBrowser {
  constructor(roots = ['/media', '/share']) {
    this.roots = roots.map((root) => path.resolve(root));
  }

  async resolve(input) {
    if (typeof input !== 'string' || !path.isAbsolute(input) || input.includes('\0')) {
      throw new Error('Zadejte úplnou cestu ke složce v Home Assistantu.');
    }
    const target = path.resolve(input);
    const root = this.roots.find((candidate) => inside(candidate, target));
    if (!root) throw new Error('Složka musí být v připojeném úložišti /media nebo /share.');
    // Reject links in every component, including the mount itself.
    let current = root;
    for (const part of ['', ...path.relative(root, target).split(path.sep).filter(Boolean)]) {
      current = part ? path.join(current, part) : current;
      const stat = await fsp.lstat(current);
      if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error('Vyberte skutečnou složku, nikoli symbolický odkaz.');
    }
    return { target, root };
  }

  async browse(input) {
    const { target, root } = await this.resolve(input);
    const directories = [];
    const texFiles = [];
    for (const item of await fsp.readdir(target, { withFileTypes: true })) {
      if (item.name.startsWith('.') || item.isSymbolicLink()) continue;
      if (item.isDirectory()) directories.push({ name: item.name, path: path.join(target, item.name) });
      else if (item.isFile() && /\.tex$/i.test(item.name)) texFiles.push(item.name);
    }
    directories.sort((a, b) => a.name.localeCompare(b.name, 'cs', { numeric: true }));
    return { path: target, parent: target === root ? null : path.dirname(target), directories, texFiles, roots: this.roots };
  }

  async create(parent, name) {
    const { target } = await this.resolve(parent);
    if (typeof name !== 'string' || !name.trim() || name !== name.trim() || name.length > 100
        || /[<>:"/\\|?*\u0000-\u001f]/.test(name) || name.startsWith('.') || name.endsWith('.')) {
      throw new Error('Název složky nesmí obsahovat lomítka, tečky na okrajích ani speciální znaky.');
    }
    const destination = path.join(target, name);
    await fsp.mkdir(destination, { mode: 0o755 });
    return destination;
  }
}

// Saving shared documents must preserve their permissions and parent directories.
async function writeShared(file, content) {
  await fsp.mkdir(path.dirname(file), { recursive: true, mode: 0o755 });
  let stat;
  try { stat = await fsp.lstat(file); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (stat && !stat.isFile()) throw new Error('Cílová položka není běžný soubor.');
  const temporary = `${file}.${crypto.randomUUID()}.tmp`;
  try {
    await fsp.writeFile(temporary, content, { mode: stat ? stat.mode & 0o777 : 0o644, flag: 'wx' });
    if (stat && process.getuid?.() === 0) await fsp.chown(temporary, stat.uid, stat.gid);
    await fsp.rename(temporary, file);
  } finally { await fsp.rm(temporary, { force: true }); }
}

async function snapshotSources(source, destination) {
  await fsp.mkdir(destination, { recursive: true });
  for (const item of await fsp.readdir(source, { withFileTypes: true })) {
    if (item.name === '.git' || item.name.startsWith('.oleaf-')) continue;
    if (item.isSymbolicLink()) throw new Error('Projekt obsahuje symbolický odkaz. Před kompilací jej odstraňte.');
    const from = path.join(source, item.name);
    const to = path.join(destination, item.name);
    if (item.isDirectory()) await snapshotSources(from, to);
    else if (item.isFile()) await fsp.copyFile(from, to, fs.constants.COPYFILE_EXCL);
  }
}

module.exports = { FolderBrowser, writeShared, snapshotSources };
