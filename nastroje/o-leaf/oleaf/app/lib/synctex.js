'use strict';

const path = require('node:path');

const numericFields = new Set(['Page', 'Line', 'Column', 'x', 'y', 'h', 'v', 'W', 'H']);

function parseSyncTex(output) {
  const records = [];
  let record = {};
  const push = () => {
    if (Object.keys(record).length) records.push(record);
    record = {};
  };
  for (const rawLine of String(output || '').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || /^SyncTeX result (?:begin|end)$/i.test(line)) {
      if (/end$/i.test(line)) push();
      continue;
    }
    const separator = line.indexOf(':');
    if (separator < 1) continue;
    const key = line.slice(0, separator);
    const value = line.slice(separator + 1);
    if (key === 'Output' && Object.keys(record).length) push();
    record[key] = numericFields.has(key) ? Number(value) : value;
  }
  push();
  return records.filter((item) => Object.values(item).some((value) => value !== '' && value != null));
}

function projectRelativeInput(projectRoot, input) {
  if (typeof input !== 'string' || !input.trim()) throw new Error('SyncTeX nevrátil zdrojový soubor.');
  const absolute = path.resolve(projectRoot, input.trim());
  const relative = path.relative(projectRoot, absolute);
  if (!relative || relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error('SyncTeX ukázal mimo otevřený projekt.');
  }
  return relative.split(path.sep).join('/');
}

function firstForwardRecord(output) {
  const record = parseSyncTex(output).find((item) => (
    Number.isInteger(item.Page) && item.Page > 0
    && Number.isFinite(item.x) && Number.isFinite(item.y)
  ));
  if (!record) throw new Error('Pro tento řádek nebyla v PDF nalezena odpovídající pozice.');
  return { page: record.Page, x: record.x, y: record.y, width: record.W, height: record.H };
}

function firstReverseRecord(output, projectRoot) {
  const record = parseSyncTex(output).find((item) => item.Input && Number.isFinite(item.Line));
  if (!record) throw new Error('Na tomto místě PDF nebyl nalezen odpovídající zdrojový řádek.');
  return {
    path: projectRelativeInput(projectRoot, record.Input),
    line: Math.max(1, Math.round(record.Line)),
    column: Number.isFinite(record.Column) && record.Column >= 0 ? Math.round(record.Column) : 0,
  };
}

module.exports = { firstForwardRecord, firstReverseRecord, parseSyncTex, projectRelativeInput };
