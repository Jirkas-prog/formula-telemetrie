'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const net = require('node:net');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const AdmZip = require('adm-zip');

test('projects API: linked folders, persistence, isolation and legacy ZIP projects', async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'oleaf-api-'));
  const media = path.join(root, 'media');
  const projectPath = path.join(media, 'projects', 'Český projekt');
  const config = path.join(root, 'config');
  await fs.mkdir(projectPath, { recursive: true });
  await fs.writeFile(path.join(projectPath, 'report.tex'), 'original');
  const portProbe = net.createServer();
  portProbe.listen(0, '127.0.0.1'); await once(portProbe, 'listening');
  const port = portProbe.address().port;
  await new Promise((resolve) => portProbe.close(resolve));
  let child;
  const stop = async () => { if (child && child.exitCode === null) { const exited = once(child, 'exit'); child.kill(); await exited; } };
  t.after(async () => { await stop(); await fs.rm(root, { recursive: true, force: true }); });
  const start = async () => {
    child = spawn(process.execPath, ['server.js'], {
      cwd: path.join(__dirname, '..'), windowsHide: true,
      env: { ...process.env, PORT: String(port), OLEAF_CONFIG_DIR: config, OLEAF_RUNTIME_DIR: path.join(root, 'data'), OLEAF_FOLDER_ROOTS: JSON.stringify([media]) },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Server startup timeout')), 30000);
      child.stdout.on('data', (data) => { if (String(data).includes('poslouchá')) { clearTimeout(timeout); resolve(); } });
      child.once('exit', (code) => { clearTimeout(timeout); reject(new Error(`Server exited: ${code}`)); });
    });
  };
  const request = async (url, body, method = body ? 'POST' : 'GET', cookie = '') => {
    const response = await fetch(`http://127.0.0.1:${port}/api/${url}`, { method, headers: { 'Content-Type': 'application/json', ...(cookie ? { Cookie: cookie } : {}) }, body: body ? JSON.stringify(body) : undefined });
    return { status: response.status, data: response.status === 204 ? null : await response.json(), cookie: response.headers.get('set-cookie')?.split(';')[0] };
  };
  await start();
  await t.test('persist and validate the default folder', async () => {
    assert.equal((await request('settings', { projectsDirectory: path.dirname(projectPath) }, 'PUT')).status, 200);
    assert.equal((await request('folders')).data.path, path.dirname(projectPath));
    assert.equal((await request('settings', { projectsDirectory: root }, 'PUT')).status, 400);
    assert.equal((await request('folders?path=' + encodeURIComponent(root))).status, 400);
  });
  let linked;
  await t.test('open folder without moving files, avoid duplicate projects, persist entry', async () => {
    linked = (await request('projects/open-folder', { path: projectPath })).data;
    assert.equal(linked.entry, 'report.tex');
    assert.equal(linked.externalPath, projectPath);
    assert.equal((await request('projects/open-folder', { path: projectPath })).data.id, linked.id);
    assert.deepEqual(await fs.readdir(projectPath), ['report.tex']);
    assert.equal((await request(`projects/${linked.id}/file?path=report.tex`)).data.content, 'original');
    assert.equal((await request(`projects/${linked.id}/file`, { path: 'report.tex', content: 'saved in place' }, 'PUT')).status, 200);
    assert.equal(await fs.readFile(path.join(projectPath, 'report.tex'), 'utf8'), 'saved in place');
    assert.equal((await request(`projects/${linked.id}/settings`, { entry: 'report.tex' }, 'PUT')).status, 200);
    assert.equal((await request(`projects/${linked.id}/file?path=../outside.txt`)).status, 400);
  });
  await t.test('new shared project, collisions, folder creation and user isolation', async () => {
    assert.equal((await request('folders', { parentPath: media, name: 'new folder' })).status, 201);
    const created = await request('projects', { name: 'New document', parentPath: media });
    assert.equal(created.status, 201);
    assert.ok((await fs.readFile(path.join(media, 'New document', 'main.tex'), 'utf8')).includes('documentclass'));
    assert.equal((await request('projects', { name: 'New document', parentPath: media })).status, 400);
    const user = await request('auth/register', { username: 'testuser', password: 'temporary-test-password' });
    assert.equal(user.status, 201);
    assert.deepEqual((await request('projects', null, 'GET', user.cookie)).data, []);
    assert.equal((await request(`projects/${linked.id}/tree`, null, 'GET', user.cookie)).status, 404);
  });
  await t.test('settings and linked projects survive restart', async () => {
    await stop(); await start();
    assert.equal((await request('settings')).data.projectsDirectory, path.dirname(projectPath));
    assert.equal((await request(`projects/${linked.id}/file?path=report.tex`)).data.content, 'saved in place');
    assert.equal((await request('projects')).data.find((p) => p.id === linked.id).entry, 'report.tex');
  });
  await t.test('linked folder compiles under an isolated UID and produces PDF and SyncTeX', {
    skip: process.env.OLEAF_TEST_TEX !== 'true',
  }, async () => {
    await fs.chmod(root, 0o751);
    const tex = '\\documentclass{article}\n\\begin{document}\nHello O-Leaf.\n\\end{document}\n';
    await request(`projects/${linked.id}/file`, { path: 'report.tex', content: tex }, 'PUT');
    const before = await fs.stat(projectPath);
    const compile = await request(`projects/${linked.id}/compile`, { entry: 'report.tex' });
    assert.equal(compile.status, 200, compile.data.log);
    assert.equal(compile.data.ok, true);
    const pdf = await fetch(`http://127.0.0.1:${port}/api/projects/${linked.id}/pdf?entry=report.tex`);
    assert.equal(Buffer.from(await pdf.arrayBuffer()).subarray(0, 5).toString(), '%PDF-');
    const forward = await request(`projects/${linked.id}/synctex/forward`, { entry: 'report.tex', path: 'report.tex', line: 3, column: 1 });
    assert.equal(forward.status, 200, JSON.stringify(forward.data));
    assert.equal(forward.data.page, 1);
    assert.deepEqual(await fs.readdir(projectPath), ['report.tex']);
    const after = await fs.stat(projectPath);
    assert.equal(after.mode, before.mode);
    assert.equal(after.uid, before.uid);
    await request(`projects/${linked.id}/file`, { path: 'report.tex', content: 'saved in place' }, 'PUT');
  });
  await t.test('private projects and ZIP import/export still work', async () => {
    const privateProject = (await request('projects', { name: 'Private' })).data;
    assert.ok(privateProject.id);
    const zip = new AdmZip(); zip.addFile('main.tex', Buffer.from('ZIP source'));
    const form = new FormData(); form.append('file', new Blob([zip.toBuffer()]), 'import.zip');
    const response = await fetch(`http://127.0.0.1:${port}/api/projects/import`, { method: 'POST', body: form });
    assert.equal(response.status, 201);
    const imported = await response.json();
    assert.equal((await request(`projects/${imported.id}/file?path=main.tex`)).data.content, 'ZIP source');
    const exported = await fetch(`http://127.0.0.1:${port}/api/projects/${linked.id}/export`);
    assert.equal(new AdmZip(Buffer.from(await exported.arrayBuffer())).readAsText('report.tex'), 'saved in place');
  });
  await t.test('removing a linked project only removes its local registration', async () => {
    assert.equal((await request(`projects/${linked.id}`, null, 'DELETE')).status, 204);
    assert.equal(await fs.readFile(path.join(projectPath, 'report.tex'), 'utf8'), 'saved in place');
    assert.equal((await request(`projects/${linked.id}/tree`)).status, 404);
  });
});
