'use strict';

const fsp = require('node:fs/promises');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { ensureDir, setOwnershipRecursive } = require('./files');

async function compileLatex({ projectRoot, entry, uid, timeoutSeconds, runtimeRoot, onOutput = () => {}, onProgress = () => {} }) {
  const buildDir = path.join(projectRoot, '.oleaf-build');
  const homeDir = path.join(runtimeRoot, 'compile-home', String(uid));
  await ensureDir(buildDir);
  await ensureDir(homeDir);
  await setOwnershipRecursive(buildDir, uid);
  await setOwnershipRecursive(homeDir, uid);

  const args = [
    '-xelatex',
    '-interaction=nonstopmode',
    '-halt-on-error',
    '-file-line-error',
    '-synctex=1',
    '-outdir=.oleaf-build',
    '-e',
    "$xelatex=q/xelatex -no-shell-escape -synctex=1 %O %S/",
    entry,
  ];

  return new Promise((resolve) => {
    let output = '';
    let timedOut = false;
    let settled = false;
    let xelatexPass = 0;
    const startedAt = Date.now();
    const command = `latexmk ${args.join(' ')}`;
    onProgress({ progress: 3, phase: 'Připravuji kompilátor', command });
    const child = spawn('latexmk', args, {
      cwd: projectRoot,
      uid,
      gid: uid,
      shell: false,
      env: {
        PATH: process.env.PATH,
        HOME: homeDir,
        LANG: 'C.UTF-8',
        openin_any: 'p',
        openout_any: 'p',
        max_print_line: '2000',
      },
    });
    const timer = setTimeout(() => {
      timedOut = true;
      onProgress({ progress: 95, phase: 'Ukončuji kompilaci po překročení limitu' });
      child.kill('SIGKILL');
    }, timeoutSeconds * 1000);
    const collect = (chunk) => {
      const text = chunk.toString('utf8');
      output += text;
      if (output.length > 2_000_000) output = output.slice(-2_000_000);
      onOutput(text);
      const lower = text.toLowerCase();
      if (lower.includes("applying rule 'xelatex'") || lower.includes('this is xetex')) {
        xelatexPass += 1;
        onProgress({ progress: Math.min(72, 14 + xelatexPass * 18), phase: `XeLaTeX — průchod ${xelatexPass}` });
      } else if (lower.includes("applying rule 'biber'") || lower.includes('this is biber')) {
        onProgress({ progress: 68, phase: 'Zpracovávám bibliografii (Biber)' });
      } else if (lower.includes('output written on') || lower.includes('written on .oleaf-build')) {
        onProgress({ progress: 90, phase: 'PDF vytvořeno, dokončuji kontrolu' });
      } else if (lower.includes('latexmk:')) {
        onProgress({ progress: Math.min(86, 8 + Math.floor((Date.now() - startedAt) / 1200)), phase: 'Probíhá kompilace' });
      }
    };
    child.stdout.on('data', collect);
    child.stderr.on('data', collect);
    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const log = `${output}\n${error.message}`;
      onOutput(`\n${error.message}\n`);
      resolve({ ok: false, timedOut: false, log, command, exitCode: null, durationMs: Date.now() - startedAt });
    });
    child.on('close', async (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const pdfName = `${path.basename(entry, path.extname(entry))}.pdf`;
      const pdfPath = path.join(buildDir, pdfName);
      let pdfExists = false;
      try {
        await fsp.access(pdfPath);
        pdfExists = true;
      } catch {}
      const ok = code === 0 && pdfExists;
      onProgress({ progress: 100, phase: ok ? 'Kompilace dokončena' : 'Kompilace selhala' });
      resolve({
        ok,
        timedOut,
        log: output,
        pdfName,
        command,
        exitCode: code,
        durationMs: Date.now() - startedAt,
      });
    });
  });
}

module.exports = { compileLatex };
