'use strict';

const crypto = require('node:crypto');
const { execFile } = require('node:child_process');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { promisify } = require('node:util');
const express = require('express');
const multer = require('multer');

const { FolderBrowser, writeShared, snapshotSources } = require('./lib/folders');
const folders = new FolderBrowser(process.env.OLEAF_FOLDER_ROOTS ? JSON.parse(process.env.OLEAF_FOLDER_ROOTS) : undefined);

const { AuthStore } = require('./lib/auth');
const { extractZip, projectZip } = require('./lib/archive');
const { compileLatex } = require('./lib/compiler');
const { hexPreview, kindFor, mimeFor } = require('./lib/file-preview');
const { firstForwardRecord, firstReverseRecord } = require('./lib/synctex');
const {
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
} = require('./lib/files');

const CONFIG_ROOT = path.resolve(process.env.OLEAF_CONFIG_DIR || '/config');
const RUNTIME_ROOT = path.resolve(process.env.OLEAF_RUNTIME_DIR || '/data');
const AUTH_ROOT = path.join(CONFIG_ROOT, 'auth');
const WORKSPACES_ROOT = path.join(CONFIG_ROOT, 'workspaces');
const USERS_ROOT = path.join(WORKSPACES_ROOT, 'users');
const GUEST_ROOT = path.join(WORKSPACES_ROOT, 'guest');
const PLUGINS_ROOT = path.join(CONFIG_ROOT, 'plugins');
const GUEST_UID = 20000;
const execFileAsync = promisify(execFile);

const DEFAULT_OPTIONS = {
  autosave_delay_ms: 800,
  compilation_timeout_seconds: 120,
  max_upload_mb: 100,
};

const pdfPreviewJobs = new Map();

async function cachedPdfPreviewPage(pdfPath, pdfStat, page) {
  const signature = crypto.createHash('sha256')
    .update(`${pdfPath}\0${pdfStat.size}\0${pdfStat.mtimeMs}\0r144`)
    .digest('hex');
  const cacheRoot = path.join(RUNTIME_ROOT, 'pdf-preview-cache', signature);
  const cachedPath = path.join(cacheRoot, `page-${page}.png`);
  try {
    const cachedStat = await fsp.stat(cachedPath);
    if (cachedStat.isFile() && cachedStat.size > 8) return cachedPath;
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }

  const jobKey = `${signature}:${page}`;
  if (!pdfPreviewJobs.has(jobKey)) {
    const job = (async () => {
      await ensureDir(cacheRoot);
      const nonce = crypto.randomBytes(6).toString('hex');
      const outputPrefix = path.join(cacheRoot, `.page-${page}-${nonce}`);
      const temporaryPath = `${outputPrefix}.png`;
      try {
        await execFileAsync('pdftoppm', [
          '-f', String(page), '-l', String(page), '-singlefile', '-png', '-r', '144', pdfPath, outputPrefix,
        ], { timeout: 30_000, maxBuffer: 2 * 1024 * 1024 });
        const renderedStat = await fsp.stat(temporaryPath);
        if (!renderedStat.isFile() || renderedStat.size <= 8) throw new Error('Vykreslená strana PDF je prázdná.');
        await fsp.rename(temporaryPath, cachedPath);
      } finally {
        await fsp.rm(temporaryPath, { force: true });
      }
    })();
    pdfPreviewJobs.set(jobKey, job);
    job.then(
      () => pdfPreviewJobs.delete(jobKey),
      () => pdfPreviewJobs.delete(jobKey),
    );
  }
  await pdfPreviewJobs.get(jobKey);
  return cachedPath;
}

function cleanProjectName(value) {
  if (typeof value !== 'string') throw new Error('Název projektu chybí.');
  const name = value.trim().replace(/[\u0000-\u001f]/g, '');
  if (!name || name.length > 80) throw new Error('Název projektu musí mít 1–80 znaků.');
  return name;
}

function parseCookies(header = '') {
  return Object.fromEntries(header.split(';').map((part) => {
    const index = part.indexOf('=');
    if (index < 0) return null;
    return [decodeURIComponent(part.slice(0, index).trim()), decodeURIComponent(part.slice(index + 1).trim())];
  }).filter(Boolean));
}

function cookieOptions(req) {
  return {
    httpOnly: true,
    sameSite: 'strict',
    secure: req.secure || req.headers['x-forwarded-proto'] === 'https',
    maxAge: 30 * 24 * 60 * 60 * 1000,
    path: '/',
  };
}

async function loadOptions() {
  const supplied = await readJson(path.join(RUNTIME_ROOT, 'options.json'), {});
  return {
    autosave_delay_ms: Math.min(10000, Math.max(250, Number(supplied.autosave_delay_ms) || DEFAULT_OPTIONS.autosave_delay_ms)),
    compilation_timeout_seconds: Math.min(600, Math.max(10, Number(supplied.compilation_timeout_seconds) || DEFAULT_OPTIONS.compilation_timeout_seconds)),
    max_upload_mb: Math.min(500, Math.max(1, Number(supplied.max_upload_mb) || DEFAULT_OPTIONS.max_upload_mb)),
  };
}

async function initializeStorage(auth) {
  await ensureDir(CONFIG_ROOT, 0o751);
  await ensureDir(RUNTIME_ROOT, 0o700);
  await ensureDir(WORKSPACES_ROOT, 0o711);
  await ensureDir(USERS_ROOT, 0o711);
  await ensureDir(PLUGINS_ROOT, 0o755);
  await ensureDir(GUEST_ROOT, 0o700);
  await ensureDir(path.join(GUEST_ROOT, 'projects'), 0o700);
  await setOwnershipRecursive(GUEST_ROOT, GUEST_UID);
  await auth.init();
}

async function ensureWorkspace(context) {
  const root = context.user ? path.join(USERS_ROOT, context.user.id) : GUEST_ROOT;
  const projectsRoot = path.join(root, 'projects');
  await ensureDir(projectsRoot, 0o700);
  await setOwnershipRecursive(root, context.uid);
  return { root, projectsRoot };
}

async function projectRecord(projectsRoot, projectId) {
  if (!/^[0-9a-f-]{36}$/i.test(projectId)) throw new Error('Neplatný identifikátor projektu.');
  const root = path.join(projectsRoot, projectId);
  const metadata = await readJson(path.join(root, '.oleaf-project.json'), null);
  if (!metadata) {
    const error = new Error('Projekt nebyl nalezen.');
    error.status = 404;
    throw error;
  }
  const storageRoot = root;
  const sourceRoot = metadata.externalPath ? (await folders.resolve(metadata.externalPath)).target : root;
  return { root: sourceRoot, storageRoot, buildRoot: metadata.externalPath ? path.join(storageRoot, '.oleaf-source') : root, metadata };

}

async function createProject(context, name, withMain = true) {
  const { projectsRoot } = await ensureWorkspace(context);
  const id = crypto.randomUUID();
  const root = path.join(projectsRoot, id);
  const metadata = {
    id,
    name: cleanProjectName(name),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    pinnedFiles: [],
  };
  await ensureDir(root, 0o700);
  await writeJson(path.join(root, '.oleaf-project.json'), metadata);
  if (withMain) {
    const starter = String.raw`\documentclass{article}
\usepackage[czech]{babel}
\usepackage{fontspec}
\title{Nový dokument}
\author{}
\date{\today}

\begin{document}
\maketitle

Začněte psát v O-Leafu.

\end{document}
`;
    await atomicWrite(path.join(root, 'main.tex'), starter);
  }
  await setOwnershipRecursive(root, context.uid);
  return metadata;
}

async function listProjects(context) {
  const { projectsRoot } = await ensureWorkspace(context);
  const result = [];
  for (const entry of await fsp.readdir(projectsRoot, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const metadata = await readJson(path.join(projectsRoot, entry.name, '.oleaf-project.json'), null);
    if (metadata) result.push(metadata);
  }
  return result.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

async function touchProject(project) {
  project.metadata.updatedAt = new Date().toISOString();
  await writeJson(path.join(project.storageRoot, '.oleaf-project.json'), project.metadata);
}

async function linkProject(context, selectedPath) {
  const { target, root: mountRoot } = await folders.resolve(selectedPath);
  if (target === mountRoot) throw new Error('Vyberte konkrétní složku projektu uvnitř úložiště.');
  await fsp.access(target, fs.constants.R_OK | fs.constants.W_OK);
  const existing = (await listProjects(context)).find((item) => item.externalPath === target);
  if (existing) return existing;
  const tree = await projectTree(target);
  const tex = [];
  const visit = (nodes) => nodes.forEach((node) => node.type === 'directory' ? visit(node.children) : /\.tex$/i.test(node.path) && tex.push(node.path));
  visit(tree);
  const metadata = await createProject(context, path.basename(target), false);
  metadata.externalPath = target;
  metadata.entry = tex.includes('main.tex') ? 'main.tex' : tex[0] || 'main.tex';
  const { projectsRoot } = await ensureWorkspace(context);
  await writeJson(path.join(projectsRoot, metadata.id, '.oleaf-project.json'), metadata);
  return metadata;
}

async function prepareCompilation(project, uid) {
  if (!project.metadata.externalPath) return project.root;
  // A compiler never runs as root or changes ownership on shared media.
  await fsp.rm(project.buildRoot, { recursive: true, force: true });
  await snapshotSources(project.root, project.buildRoot);
  await setOwnershipRecursive(project.buildRoot, uid);
  return project.buildRoot;
}

const activeBuilds = new Set();
async function compileProject(project, options) {
  if (activeBuilds.has(project.buildRoot)) {
    const error = new Error('Tento projekt se už kompiluje.'); error.status = 409; throw error;
  }
  activeBuilds.add(project.buildRoot);
  try {
    const projectRoot = await prepareCompilation(project, options.uid);
    return await compileLatex({ ...options, projectRoot });
  } finally { activeBuilds.delete(project.buildRoot); }
}

async function main() {
  const options = await loadOptions();
  const auth = new AuthStore(AUTH_ROOT);
  await initializeStorage(auth);

  const app = express();
  app.set('trust proxy', 1);
  app.disable('x-powered-by');

  app.use((req, res, next) => {
    const remote = req.socket.remoteAddress || '';
    const allowed = process.env.OLEAF_ALLOW_DIRECT === 'true'
      || ['172.30.32.2', '::ffff:172.30.32.2', '127.0.0.1', '::1'].includes(remote);
    if (!allowed) return res.status(403).send('O-Leaf je dostupný pouze přes Home Assistant Ingress.');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
    next();
  });

  app.use(express.json({ limit: '6mb' }));
  const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: options.max_upload_mb * 1024 * 1024, files: 1 },
  });

  app.use(async (req, _res, next) => {
    try {
      const token = parseCookies(req.headers.cookie).oleaf_session;
      const user = await auth.session(token);
      req.oleaf = { token, user, uid: user ? user.compileUid : GUEST_UID };
      next();
    } catch (error) {
      next(error);
    }
  });

  app.get('/health', (_req, res) => res.json({ status: 'ok' }));

  app.get('/api/session', async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.json({
      authenticated: Boolean(req.oleaf.user),
      user: req.oleaf.user ? { username: req.oleaf.user.username } : null,
      workspace: req.oleaf.user ? 'user' : 'guest',
      options: { autosaveDelayMs: options.autosave_delay_ms },
    });
  });

  app.post('/api/auth/register', async (req, res) => {
    await auth.register(req.body.username, req.body.password);
    const login = await auth.login(req.body.username, req.body.password);
    await ensureWorkspace({ user: login.user, uid: login.user.compileUid });
    res.cookie('oleaf_session', login.token, cookieOptions(req));
    res.status(201).json({ username: login.user.username });
  });

  app.post('/api/auth/login', async (req, res) => {
    const login = await auth.login(req.body.username, req.body.password);
    await ensureWorkspace({ user: login.user, uid: login.user.compileUid });
    res.cookie('oleaf_session', login.token, cookieOptions(req));
    res.json({ username: login.user.username });
  });

  app.post('/api/auth/logout', async (req, res) => {
    await auth.logout(req.oleaf.token);
    res.clearCookie('oleaf_session', { path: '/' });
    res.status(204).end();
  });

  const folderSettings = async (context) => {
    const { root } = await ensureWorkspace(context);
    const supplied = await readJson(path.join(RUNTIME_ROOT, 'options.json'), {});
    return readJson(path.join(root, 'settings.json'), { projectsDirectory: supplied.projects_directory || '/media/projekty/latex' });
  };

  app.get('/api/settings', async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.json({ ...await folderSettings(req.oleaf), roots: folders.roots });
  });
  app.put('/api/settings', async (req, res) => {
    const { target } = await folders.resolve(req.body.projectsDirectory);
    await fsp.access(target, fs.constants.R_OK | fs.constants.W_OK);
    const { root } = await ensureWorkspace(req.oleaf);
    await writeJson(path.join(root, 'settings.json'), { projectsDirectory: target });
    res.json({ projectsDirectory: target, roots: folders.roots });
  });
  app.get('/api/folders', async (req, res) => {
    const settings = await folderSettings(req.oleaf);
    res.setHeader('Cache-Control', 'no-store');
    res.json(await folders.browse(req.query.path || settings.projectsDirectory));
  });
  app.post('/api/folders', async (req, res) => {
    const created = await folders.create(req.body.parentPath, req.body.name);
    res.status(201).json({ path: created });
  });
  app.post('/api/projects/open-folder', async (req, res) => {
    res.json(await linkProject(req.oleaf, req.body.path));
  });
  app.put('/api/projects/:projectId/settings', async (req, res) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const entry = resolveInside(project.root, req.body.entry);
    if (!/\.tex$/i.test(entry.clean) || !(await fsp.lstat(entry.target)).isFile()) throw new Error('Vyberte existující soubor .tex.');
    project.metadata.entry = entry.clean;
    await touchProject(project);
    res.json(project.metadata);
  });

  app.get('/api/projects', async (req, res) => res.json(await listProjects(req.oleaf)));

  app.post('/api/projects', async (req, res) => {
    if (req.body.parentPath) {
      const name = cleanProjectName(req.body.name);
      const destination = await folders.create(req.body.parentPath, name);
      // The new directory is exclusive; no existing document can be overwritten.
      await writeShared(path.join(destination, 'main.tex'), String.raw`\documentclass{article}
\usepackage[czech]{babel}
\usepackage{fontspec}
\begin{document}
Nový dokument.
\end{document}
`);
      return res.status(201).json(await linkProject(req.oleaf, destination));
    }
    const project = await createProject(req.oleaf, req.body.name || 'Nový projekt');
    res.status(201).json(project);
  });

  app.delete('/api/projects/:projectId', async (req, res) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    await fsp.rm(project.storageRoot, { recursive: true, force: false });
    res.status(204).end();
  });

  app.get('/api/projects/:projectId/tree', async (req, res) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    res.json(await projectTree(project.root));
  });

  app.get('/api/projects/:projectId/pins', async (req, res) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const stored = Array.isArray(project.metadata.pinnedFiles) ? project.metadata.pinnedFiles : [];
    const paths = [];
    for (const candidate of stored) {
      try {
        const { clean, target } = resolveInside(project.root, candidate);
        if ((await fsp.lstat(target)).isFile() && !paths.includes(clean)) paths.push(clean);
      } catch {
        // Staré připnutí se po smazání nebo ruční změně projektu samo uklidí.
      }
    }
    if (JSON.stringify(paths) !== JSON.stringify(stored)) {
      project.metadata.pinnedFiles = paths;
      await writeJson(path.join(project.storageRoot, '.oleaf-project.json'), project.metadata);
    }
    res.setHeader('Cache-Control', 'no-store');
    res.json({ paths });
  });

  app.put('/api/projects/:projectId/pins', async (req, res) => {
    if (!Array.isArray(req.body.paths) || req.body.paths.length > 100) {
      throw new Error('Seznam připnutých souborů je neplatný nebo příliš dlouhý.');
    }
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const paths = [];
    for (const candidate of req.body.paths) {
      const { clean, target } = resolveInside(project.root, candidate);
      const stat = await fsp.lstat(target);
      if (!stat.isFile()) throw new Error(`Připnout lze pouze soubor: ${clean}`);
      if (!paths.includes(clean)) paths.push(clean);
    }
    project.metadata.pinnedFiles = paths;
    await touchProject(project);
    res.json({ paths, savedAt: project.metadata.updatedAt });
  });

  app.get('/api/projects/:projectId/file', async (req, res) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const { clean, target } = resolveInside(project.root, String(req.query.path || ''));
    const stat = await fsp.lstat(target);
    if (!stat.isFile()) throw new Error('Vybraná položka není soubor.');
    const editable = stat.size <= 5 * 1024 * 1024;
    const handle = await fsp.open(target, 'r');
    let probe;
    try {
      const length = Math.min(stat.size, editable ? 5 * 1024 * 1024 : 4096);
      probe = Buffer.alloc(length);
      if (length) await handle.read(probe, 0, length, 0);
    } finally { await handle.close(); }
    const kind = kindFor(clean, probe, editable && probe.length === stat.size);
    const payload = { path: clean, kind, mime: mimeFor(clean), bytes: stat.size };
    if (kind === 'text') payload.content = probe.toString('utf8');
    if (kind === 'binary') payload.hex = hexPreview(probe);
    res.setHeader('Cache-Control', 'no-store');
    res.json(payload);
  });

  const rawProjectFile = async (req) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const file = resolveInside(project.root, String(req.query.path || ''));
    const stat = await fsp.lstat(file.target);
    if (!stat.isFile()) throw new Error('Vybraná položka není soubor.');
    return { ...file, stat };
  };

  app.get('/api/projects/:projectId/file/raw', async (req, res) => {
    const file = await rawProjectFile(req);
    const safeName = path.basename(file.clean).replace(/[\r\n"]/g, '_');
    const download = req.query.download === '1';
    let responseMime = mimeFor(file.clean);
    if (!download) {
      const length = Math.min(file.stat.size, 512);
      const probe = Buffer.alloc(length);
      const handle = await fsp.open(file.target, 'r');
      try { if (length) await handle.read(probe, 0, length, 0); } finally { await handle.close(); }
      const inlineKind = kindFor(file.clean, probe, false);
      if (!['pdf', 'image', 'audio', 'video'].includes(inlineKind)) responseMime = 'application/octet-stream';
    }
    res.setHeader('Cache-Control', 'private, no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    if (!download) res.setHeader('Content-Security-Policy', 'sandbox');
    res.setHeader('Content-Disposition', `${download ? 'attachment' : 'inline'}; filename="${safeName}"`);
    res.type(responseMime).sendFile(file.target, { dotfiles: 'allow' });
  });

  const assertPdfFile = async (file) => {
    const probe = Buffer.alloc(5);
    const handle = await fsp.open(file.target, 'r');
    try { await handle.read(probe, 0, 5, 0); } finally { await handle.close(); }
    if (probe.toString('ascii') !== '%PDF-') throw new Error('Vybraný soubor není platné PDF.');
  };

  app.get('/api/projects/:projectId/file/pdf/info', async (req, res) => {
    const file = await rawProjectFile(req);
    await assertPdfFile(file);
    const { stdout } = await execFileAsync('pdfinfo', [file.target], { encoding: 'utf8', timeout: 10_000, maxBuffer: 1024 * 1024 });
    const pages = Number.parseInt((/^Pages:\s+(\d+)/m.exec(stdout) || [])[1], 10);
    if (!Number.isInteger(pages) || pages < 1 || pages > 500) throw new Error('Nelze určit počet stran PDF.');
    const version = crypto.createHash('sha256').update(`${file.target}\0${file.stat.size}\0${file.stat.mtimeMs}`).digest('hex').slice(0, 20);
    res.setHeader('Cache-Control', 'no-store');
    res.json({ path: file.clean, pages, bytes: file.stat.size, version });
  });

  app.get('/api/projects/:projectId/file/pdf/page/:page', async (req, res) => {
    const page = Number.parseInt(req.params.page, 10);
    if (!Number.isInteger(page) || page < 1 || page > 500) throw new Error('Neplatné číslo strany PDF.');
    const file = await rawProjectFile(req);
    await assertPdfFile(file);
    const previewPath = await cachedPdfPreviewPage(file.target, file.stat, page);
    res.setHeader('Cache-Control', 'private, max-age=31536000, immutable');
    res.type('image/png').sendFile(previewPath, { dotfiles: 'allow' });
  });

  app.put('/api/projects/:projectId/file', async (req, res) => {
    if (typeof req.body.content !== 'string' || Buffer.byteLength(req.body.content) > 5 * 1024 * 1024) {
      throw new Error('Obsah souboru je příliš velký nebo neplatný.');
    }
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const { clean, target } = resolveInside(project.root, req.body.path);
    if (fs.existsSync(target) && (await fsp.lstat(target)).isSymbolicLink()) throw new Error('Symbolické odkazy nejsou povoleny.');
    await (project.metadata.externalPath ? writeShared : atomicWrite)(target, req.body.content);
    await touchProject(project);
    if (!project.metadata.externalPath) await setOwnershipRecursive(project.root, req.oleaf.uid);
    res.json({ path: clean, savedAt: project.metadata.updatedAt });
  });

  app.post('/api/projects/:projectId/node', async (req, res) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const { clean, target } = resolveInside(project.root, req.body.path);
    if (fs.existsSync(target)) throw new Error('Soubor nebo složka už existuje.');
    if (req.body.type === 'directory') await fsp.mkdir(target, { recursive: true, mode: project.metadata.externalPath ? 0o755 : 0o700 });
    else await (project.metadata.externalPath ? writeShared : atomicWrite)(target, '');
    await touchProject(project);
    if (!project.metadata.externalPath) await setOwnershipRecursive(project.root, req.oleaf.uid);
    res.status(201).json({ path: clean, type: req.body.type === 'directory' ? 'directory' : 'file' });
  });

  app.post('/api/projects/:projectId/rename', async (req, res) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const source = resolveInside(project.root, req.body.from);
    const destination = resolveInside(project.root, req.body.to);
    if (fs.existsSync(destination.target)) throw new Error('Cílová cesta už existuje.');
    await fsp.mkdir(path.dirname(destination.target), { recursive: true, mode: project.metadata.externalPath ? 0o755 : 0o700 });
    await fsp.rename(source.target, destination.target);
    if (Array.isArray(project.metadata.pinnedFiles)) {
      project.metadata.pinnedFiles = project.metadata.pinnedFiles.map((pinned) => {
        if (pinned === source.clean) return destination.clean;
        if (pinned.startsWith(`${source.clean}/`)) return `${destination.clean}${pinned.slice(source.clean.length)}`;
        return pinned;
      });
    }
    await touchProject(project);
    res.json({ path: destination.clean });
  });

  app.delete('/api/projects/:projectId/node', async (req, res) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const { clean, target } = resolveInside(project.root, String(req.query.path || ''));
    await fsp.rm(target, { recursive: true, force: false });
    if (Array.isArray(project.metadata.pinnedFiles)) {
      project.metadata.pinnedFiles = project.metadata.pinnedFiles.filter((pinned) => (
        pinned !== clean && !pinned.startsWith(`${clean}/`)
      ));
    }
    await touchProject(project);
    res.status(204).end();
  });

  const compileJobs = new Map();

  const compilationTarget = async (req) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const entry = normalizeRelative(req.body.entry || 'main.tex');
    if (!entry.toLowerCase().endsWith('.tex')) throw new Error('Hlavní soubor musí mít příponu .tex.');
    const entryPath = resolveInside(project.root, entry).target;
    if (!(await fsp.lstat(entryPath)).isFile()) throw new Error('Hlavní TeX soubor neexistuje.');
    return { project, entry };
  };

  const compilationOwner = (request) => request.oleaf.user ? `user:${request.oleaf.user.id}` : 'guest';

  app.post('/api/projects/:projectId/compile/start', async (req, res) => {
    const target = await compilationTarget(req);
    const owner = compilationOwner(req);
    const active = [...compileJobs.values()].find((job) => (
      job.owner === owner && job.projectId === req.params.projectId && job.status === 'running'
    ));
    if (active) return res.status(409).json({ error: 'Tento projekt se už kompiluje.', jobId: active.id });

    const job = {
      id: crypto.randomUUID(),
      owner,
      projectId: req.params.projectId,
      entry: target.entry,
      status: 'running',
      phase: 'Čekám na kompilátor',
      progress: 1,
      log: '',
      logBase: 0,
      startedAt: new Date().toISOString(),
      finishedAt: null,
      result: null,
    };
    compileJobs.set(job.id, job);
    res.status(202).json({ jobId: job.id, status: job.status, progress: job.progress, phase: job.phase });

    setImmediate(async () => {
      try {
        const result = await compileProject(target.project, {
          entry: target.entry,
          uid: req.oleaf.uid,
          timeoutSeconds: options.compilation_timeout_seconds,
          runtimeRoot: RUNTIME_ROOT,
          onOutput: (text) => {
            job.log += text;
            if (job.log.length > 2_000_000) {
              const removed = job.log.length - 2_000_000;
              job.log = job.log.slice(removed);
              job.logBase += removed;
            }
          },
          onProgress: (update) => {
            if (Number.isFinite(update.progress)) job.progress = Math.max(job.progress, Math.min(100, update.progress));
            if (update.phase) job.phase = update.phase;
            if (update.command) job.command = update.command;
          },
        });
        job.status = result.ok ? 'complete' : 'failed';
        job.progress = 100;
        job.phase = result.ok ? 'Kompilace dokončena' : 'Kompilace selhala';
        job.finishedAt = new Date().toISOString();
        job.result = { ...result, log: undefined };
      } catch (error) {
        job.status = 'failed';
        job.progress = 100;
        job.phase = 'Kompilátor skončil chybou';
        job.finishedAt = new Date().toISOString();
        job.log += `\n[O-Leaf] ${error.stack || error.message}\n`;
        job.result = { ok: false, error: error.message, exitCode: null };
      }
    });
  });

  app.get('/api/compile/:jobId/status', async (req, res) => {
    const job = compileJobs.get(req.params.jobId);
    if (!job || job.owner !== compilationOwner(req)) return res.status(404).json({ error: 'Kompilační úloha nebyla nalezena.' });
    const requestedOffset = Math.max(0, Number.parseInt(String(req.query.offset || '0'), 10) || 0);
    const effectiveOffset = Math.max(job.logBase, requestedOffset);
    const localOffset = effectiveOffset - job.logBase;
    const skipped = requestedOffset < job.logBase ? `[O-Leaf] Starší část logu byla zkrácena (${job.logBase} znaků).\n` : '';
    res.setHeader('Cache-Control', 'no-store');
    res.json({
      id: job.id,
      status: job.status,
      phase: job.phase,
      progress: job.progress,
      entry: job.entry,
      command: job.command,
      startedAt: job.startedAt,
      finishedAt: job.finishedAt,
      logChunk: skipped + job.log.slice(localOffset),
      nextOffset: job.logBase + job.log.length,
      result: job.result,
    });
  });

  app.post('/api/projects/:projectId/compile', async (req, res) => {
    const target = await compilationTarget(req);
    const result = await compileProject(target.project, {
      entry: target.entry,
      uid: req.oleaf.uid,
      timeoutSeconds: options.compilation_timeout_seconds,
      runtimeRoot: RUNTIME_ROOT,
    });
    res.status(result.ok ? 200 : 422).json(result);
  });

  const compiledPdf = async (req) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const entry = normalizeRelative(String(req.body?.entry || req.query.entry || 'main.tex'));
    const pdfName = `${path.basename(entry, path.extname(entry))}.pdf`;
    const pdfPath = path.join(project.buildRoot, '.oleaf-build', pdfName);
    const pdfStat = await fsp.stat(pdfPath);
    if (!pdfStat.isFile() || pdfStat.size < 5) throw new Error('Výstupní PDF neexistuje nebo je prázdné.');
    const syncName = `${path.basename(entry, path.extname(entry))}.synctex.gz`;
    const syncPath = path.join(project.buildRoot, '.oleaf-build', syncName);
    return { project, entry, pdfName, pdfPath, pdfStat, syncPath };
  };

  const syncTexOutput = async (req, mode, argument) => {
    const artifact = await compiledPdf(req);
    try {
      const syncStat = await fsp.stat(artifact.syncPath);
      if (!syncStat.isFile() || syncStat.size < 10) throw new Error('Mapa SyncTeX je prázdná.');
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      const missing = new Error('Toto PDF ještě nemá mapu SyncTeX. Zkompilujte projekt znovu.');
      missing.status = 409;
      throw missing;
    }
    try {
      const resolvedArgument = typeof argument === 'function' ? argument(artifact) : argument;
      const { stdout } = await execFileAsync('synctex', [mode, mode === 'view' ? '-i' : '-o', resolvedArgument, ...(mode === 'view' ? ['-o', artifact.pdfPath] : [])], {
        cwd: artifact.project.buildRoot,
        encoding: 'utf8',
        timeout: 10_000,
        maxBuffer: 1024 * 1024,
      });
      return { artifact, stdout };
    } catch (error) {
      const detail = String(error.stdout || error.stderr || '').trim();
      const syncError = new Error(detail || 'SyncTeX nedokázal propojit zvolené místo.');
      syncError.status = 422;
      throw syncError;
    }
  };

  app.post('/api/projects/:projectId/synctex/forward', async (req, res) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const source = resolveInside(project.root, String(req.body.path || ''));
    const sourceStat = await fsp.stat(source.target);
    if (!sourceStat.isFile() || !source.clean.toLowerCase().endsWith('.tex')) {
      throw new Error('Dopřednou navigaci lze použít pouze v souboru .tex.');
    }
    const line = Number.parseInt(req.body.line, 10);
    const column = Number.parseInt(req.body.column, 10);
    if (!Number.isInteger(line) || line < 1 || line > 1_000_000) throw new Error('Neplatný řádek zdrojového souboru.');
    const safeColumn = Number.isInteger(column) ? Math.max(0, Math.min(1_000_000, column)) : 0;
    const { stdout } = await syncTexOutput(req, 'view', `${line}:${safeColumn}:${path.join(project.buildRoot, source.clean)}`);
    res.setHeader('Cache-Control', 'no-store');
    res.json(firstForwardRecord(stdout));
  });

  app.post('/api/projects/:projectId/synctex/reverse', async (req, res) => {
    const page = Number.parseInt(req.body.page, 10);
    const x = Number(req.body.x);
    const y = Number(req.body.y);
    if (!Number.isInteger(page) || page < 1 || page > 500
        || !Number.isFinite(x) || x < 0 || x > 10000
        || !Number.isFinite(y) || y < 0 || y > 10000) {
      throw new Error('Neplatná pozice v PDF.');
    }
    const { artifact, stdout } = await syncTexOutput(req, 'edit', ({ pdfPath }) => `${page}:${x.toFixed(3)}:${y.toFixed(3)}:${pdfPath}`);
    const result = firstReverseRecord(stdout, artifact.project.buildRoot);
    const source = resolveInside(artifact.project.root, result.path);
    if (!(await fsp.stat(source.target)).isFile()) throw new Error('Nalezený zdrojový soubor už neexistuje.');
    res.setHeader('Cache-Control', 'no-store');
    res.json(result);
  });

  app.get('/api/projects/:projectId/pdf', async (req, res) => {
    const { pdfName, pdfPath } = await compiledPdf(req);
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Disposition', `inline; filename="${pdfName.replaceAll('"', '')}"`);
    res.type('application/pdf').sendFile(pdfPath, { dotfiles: 'allow' });
  });

  app.get('/api/projects/:projectId/pdf/info', async (req, res) => {
    const { pdfName, pdfPath, pdfStat } = await compiledPdf(req);
    const { stdout } = await execFileAsync('pdfinfo', [pdfPath], {
      encoding: 'utf8',
      timeout: 10_000,
      maxBuffer: 1024 * 1024,
    });
    const pages = Number.parseInt((/^Pages:\s+(\d+)/m.exec(stdout) || [])[1], 10);
    if (!Number.isInteger(pages) || pages < 1 || pages > 500) throw new Error('Nelze určit počet stran PDF.');
    const version = crypto.createHash('sha256')
      .update(`${pdfPath}\0${pdfStat.size}\0${pdfStat.mtimeMs}`)
      .digest('hex')
      .slice(0, 20);
    res.setHeader('Cache-Control', 'no-store');
    res.json({ name: pdfName, pages, bytes: pdfStat.size, version });
  });

  app.get('/api/projects/:projectId/pdf/page/:page', async (req, res) => {
    const page = Number.parseInt(req.params.page, 10);
    if (!Number.isInteger(page) || page < 1 || page > 500) throw new Error('Neplatné číslo strany PDF.');
    const { pdfPath, pdfStat } = await compiledPdf(req);
    const previewPath = await cachedPdfPreviewPage(pdfPath, pdfStat, page);
    res.setHeader('Cache-Control', 'private, max-age=31536000, immutable');
    res.type('image/png').sendFile(previewPath, { dotfiles: 'allow' });
  });

  app.post('/api/projects/import', upload.single('file'), async (req, res) => {
    if (!req.file) throw new Error('Vyberte ZIP projektu.');
    const fallbackName = path.basename(req.file.originalname, path.extname(req.file.originalname));
    const metadata = await createProject(req.oleaf, req.body.name || fallbackName || 'Importovaný projekt', false);
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, metadata.id);
    try {
      await extractZip(req.file.buffer, project.root, options.max_upload_mb * 5 * 1024 * 1024);
      await writeJson(path.join(project.storageRoot, '.oleaf-project.json'), metadata);
      if (!project.metadata.externalPath) await setOwnershipRecursive(project.root, req.oleaf.uid);
      res.status(201).json(metadata);
    } catch (error) {
      await fsp.rm(project.root, { recursive: true, force: true });
      throw error;
    }
  });

  app.get('/api/projects/:projectId/export', async (req, res) => {
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    const buffer = await projectZip(project.root);
    const filename = project.metadata.name.replace(/[^\p{L}\p{N}_.-]+/gu, '_') || 'projekt';
    res.attachment(`${filename}.zip`).type('application/zip').send(buffer);
  });

  app.get('/api/plugins', async (_req, res) => {
    const plugins = [];
    for (const entry of await fsp.readdir(PLUGINS_ROOT, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const manifest = await readJson(path.join(PLUGINS_ROOT, entry.name, 'oleaf-plugin.json'), null);
      if (manifest) plugins.push(manifest);
    }
    res.json(plugins.sort((a, b) => a.name.localeCompare(b.name, 'cs')));
  });

  app.post('/api/plugins/import', upload.single('file'), async (req, res) => {
    if (!req.file) throw new Error('Vyberte ZIP pluginu.');
    const importsRoot = path.join(CONFIG_ROOT, '.plugin-imports');
    const temporary = path.join(importsRoot, crypto.randomUUID());
    await ensureDir(temporary);
    try {
      await extractZip(req.file.buffer, temporary, options.max_upload_mb * 5 * 1024 * 1024);
      const manifest = await readJson(path.join(temporary, 'oleaf-plugin.json'), null);
      if (!manifest || manifest.schemaVersion !== 1 || !validIdentifier(manifest.id)
          || typeof manifest.name !== 'string' || typeof manifest.version !== 'string') {
        throw new Error('Plugin nemá platný manifest oleaf-plugin.json.');
      }
      const contentRoot = normalizeRelative(manifest.contentRoot || 'template');
      const contentPath = path.join(temporary, contentRoot);
      if (!(await fsp.lstat(contentPath)).isDirectory()) throw new Error('Obsahová složka pluginu neexistuje.');
      const destination = path.join(PLUGINS_ROOT, manifest.id);
      if (fs.existsSync(destination)) throw new Error('Plugin se stejným ID už je nainstalovaný.');
      await fsp.rename(temporary, destination);
      await setOwnershipRecursive(destination, 0, 0);
      await fsp.chmod(destination, 0o755);
      res.status(201).json(manifest);
    } finally {
      await fsp.rm(temporary, { recursive: true, force: true }).catch(() => {});
    }
  });

  app.post('/api/projects/:projectId/apply-plugin', async (req, res) => {
    if (!validIdentifier(req.body.pluginId)) throw new Error('Neplatné ID pluginu.');
    const pluginRoot = path.join(PLUGINS_ROOT, req.body.pluginId);
    const manifest = await readJson(path.join(pluginRoot, 'oleaf-plugin.json'), null);
    if (!manifest) throw new Error('Plugin nebyl nalezen.');
    const source = resolveInside(pluginRoot, manifest.contentRoot || 'template').target;
    const { projectsRoot } = await ensureWorkspace(req.oleaf);
    const project = await projectRecord(projectsRoot, req.params.projectId);
    if (project.metadata.externalPath) {
      const copyShared = async (from, to) => {
        for (const item of await fsp.readdir(from, { withFileTypes: true })) {
          const dest = resolveInside(project.root, path.relative(project.root, path.join(to, item.name))).target;
          if (item.isSymbolicLink()) throw new Error('Symbolické odkazy nejsou povoleny.');
          if (item.isDirectory()) { await fsp.mkdir(dest, { recursive: true, mode: 0o755 }); await copyShared(path.join(from, item.name), dest); }
          else if (item.isFile() && (req.body.overwrite || !fs.existsSync(dest))) await writeShared(dest, await fsp.readFile(path.join(from, item.name)));
        }
      };
      await copyShared(source, project.root);
    } else await copyTree(source, project.root, { overwrite: Boolean(req.body.overwrite) });
    await touchProject(project);
    if (!project.metadata.externalPath) await setOwnershipRecursive(project.root, req.oleaf.uid);
    res.json({ applied: manifest.id, overwritten: Boolean(req.body.overwrite) });
  });

  app.use(express.static(path.join(__dirname, 'public'), {
    index: 'index.html',
    etag: true,
    maxAge: process.env.NODE_ENV === 'production' ? '1h' : 0,
    setHeaders(res, filePath) {
      if (filePath.endsWith('.html')) {
        res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
      }
    },
  }));

  app.use((error, _req, res, _next) => {
    const status = error.status || (error.code === 'ENOENT' ? 404 : 400);
    console.error(error);
    res.status(status).json({ error: error.message || 'Neočekávaná chyba.' });
  });

  setInterval(() => auth.consumeRecovery().catch((error) => console.error(error)), 5000).unref();
  setInterval(() => {
    const cutoff = Date.now() - 60 * 60 * 1000;
    for (const [id, job] of compileJobs.entries()) {
      const timestamp = Date.parse(job.finishedAt || job.startedAt);
      if (job.status !== 'running' && timestamp < cutoff) compileJobs.delete(id);
    }
  }, 10 * 60 * 1000).unref();

  const port = Number(process.env.PORT || 8099);
  app.listen(port, '0.0.0.0', () => {
    console.log(`O-Leaf poslouchá na portu ${port}. Data: ${CONFIG_ROOT}`);
  });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
