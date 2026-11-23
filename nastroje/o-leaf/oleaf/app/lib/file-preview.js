'use strict';

const path = require('node:path');

const MIME_TYPES = new Map(Object.entries({
  '.pdf': 'application/pdf',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.webp': 'image/webp', '.bmp': 'image/bmp', '.ico': 'image/x-icon', '.avif': 'image/avif',
  '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.oga': 'audio/ogg',
  '.m4a': 'audio/mp4', '.aac': 'audio/aac', '.flac': 'audio/flac',
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.ogv': 'video/ogg', '.mov': 'video/quicktime',
  '.txt': 'text/plain; charset=utf-8', '.tex': 'text/x-tex; charset=utf-8', '.bib': 'text/x-bibtex; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8', '.csv': 'text/csv; charset=utf-8', '.tsv': 'text/tab-separated-values; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.yaml': 'application/yaml; charset=utf-8', '.yml': 'application/yaml; charset=utf-8',
  '.xml': 'application/xml; charset=utf-8', '.svg': 'image/svg+xml; charset=utf-8', '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.cjs': 'text/javascript; charset=utf-8', '.py': 'text/x-python; charset=utf-8', '.sh': 'text/x-shellscript; charset=utf-8',
  '.sty': 'text/x-tex; charset=utf-8', '.cls': 'text/x-tex; charset=utf-8', '.dtx': 'text/x-tex; charset=utf-8',
  '.log': 'text/plain; charset=utf-8', '.aux': 'text/plain; charset=utf-8', '.bbl': 'text/plain; charset=utf-8',
  '.blg': 'text/plain; charset=utf-8', '.toc': 'text/plain; charset=utf-8', '.out': 'text/plain; charset=utf-8',
  '.toml': 'text/plain; charset=utf-8', '.ini': 'text/plain; charset=utf-8', '.conf': 'text/plain; charset=utf-8',
}));

const imageExtensions = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.avif', '.svg']);
const audioExtensions = new Set(['.mp3', '.wav', '.ogg', '.oga', '.m4a', '.aac', '.flac']);
const videoExtensions = new Set(['.mp4', '.webm', '.ogv', '.mov']);

function mimeFor(filePath) {
  return MIME_TYPES.get(path.extname(filePath).toLowerCase()) || 'application/octet-stream';
}

function isUtf8Text(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.includes(0)) return false;
  try {
    new TextDecoder('utf-8', { fatal: true }).decode(buffer);
    return true;
  } catch {
    return false;
  }
}

function kindFor(filePath, buffer, complete = true) {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === '.pdf' && buffer.subarray(0, 5).toString('ascii') === '%PDF-') return 'pdf';
  if (imageExtensions.has(extension)) return 'image';
  if (audioExtensions.has(extension)) return 'audio';
  if (videoExtensions.has(extension)) return 'video';
  if (complete && isUtf8Text(buffer)) return 'text';
  return 'binary';
}

function hexPreview(buffer, maximum = 512) {
  const view = buffer.subarray(0, maximum);
  const lines = [];
  for (let offset = 0; offset < view.length; offset += 16) {
    const slice = view.subarray(offset, offset + 16);
    const hex = [...slice].map((value) => value.toString(16).padStart(2, '0')).join(' ').padEnd(47);
    const ascii = [...slice].map((value) => (value >= 32 && value < 127 ? String.fromCharCode(value) : '·')).join('');
    lines.push(`${offset.toString(16).padStart(8, '0')}  ${hex}  ${ascii}`);
  }
  return lines.join('\n');
}

module.exports = { hexPreview, isUtf8Text, kindFor, mimeFor };
