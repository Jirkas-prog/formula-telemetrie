/* global CodeMirror, OLeafUI */
'use strict';

const DEFAULT_APPEARANCE = {
  theme: 'workflow',
  fontSize: 14,
  editorZoom: 100,
  pdfZoom: 100,
  wordWrap: false,
  consoleHeight: 220,
  consoleCollapsed: true,
};

const state = {
  session: null,
  projects: [],
  plugins: [],
  project: null,
  projectTree: [],
  pinnedFiles: [],
  file: null,
  fileKind: null,
  fileMime: null,
  loadingFile: false,
  openFileRequest: 0,
  filePreviewToken: 0,
  dirty: false,
  saving: false,
  saveTimer: null,
  authMode: 'login',
  collapsedDirs: new Set(),
  pdfObjectUrl: null,
  pdfDirectUrl: null,
  pdfBlob: null,
  pdfPage: 0,
  pdfPages: 0,
  pdfRevision: 0,
  pdfLoadToken: 0,
  pdfObserver: null,
  pdfScrollFrame: null,
  compileJobId: null,
  compileCommandLogged: false,
  consoleBuffer: '',
  appearance: { ...DEFAULT_APPEARANCE },
  appearanceSaveTimer: null,
  syncRequest: 0,
  syncLineHandle: null,
  syncLineTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const elements = {
  workspace: $('.workspace'),
  workspaceBadge: $('#workspace-badge'),
  accountButton: $('#account-button'),
  fileTree: $('#file-tree'),
  pinnedSection: $('#pinned-section'),
  pinnedFiles: $('#pinned-files'),
  currentPath: $('#current-path'),
  filePreview: $('#file-preview'),
  dirtyDot: $('#dirty-dot'),
  saveState: $('#save-state'),
  entryFile: $('#entry-file'),
  pdfRenderer: $('#pdf-renderer'),
  pdfPages: $('#pdf-pages'),
  pdfPageLabel: $('#pdf-page-label'),
  pdfPrev: $('#pdf-prev'),
  pdfNext: $('#pdf-next'),
  previewPlaceholder: $('#preview-placeholder'),
  openPdf: $('#open-pdf'),
  downloadPdf: $('#download-pdf'),
  editorZoomLabel: $('#editor-zoom-label'),
  pdfZoomLabel: $('#pdf-zoom-label'),
  toast: $('#toast'),
  projectUpload: $('#project-upload'),
  pluginUpload: $('#plugin-upload'),
  authDialog: $('#auth-dialog'),
  authTitle: $('#auth-title'),
  authDescription: $('#auth-description'),
  authForm: $('#auth-form'),
  authUsername: $('#auth-username'),
  authPassword: $('#auth-password'),
  authError: $('#auth-error'),
  authSwitch: $('#auth-switch'),
  authSubmit: $('#auth-submit'),
  settingsDialog: $('#settings-dialog'),
  settingsForm: $('#settings-form'),
  progressWrap: $('#compile-progress-wrap'),
  progressBar: $('#compile-progress-bar'),
  progressLabel: $('#compile-progress-label'),
  progressPercent: $('#compile-progress-percent'),
  debugConsole: $('#debug-console'),
  consoleIndicator: $('#console-indicator'),
  consoleSummary: $('#console-summary'),
};

class OLeafDropdown {
  constructor(root, onChange) {
    this.root = root;
    this.button = root.querySelector('.dropdown-toggle');
    this.label = root.querySelector('.dropdown-label');
    this.menu = root.querySelector('.dropdown-menu');
    this.placeholder = root.dataset.placeholder || 'Vyberte';
    this.onChange = onChange;
    this.items = [];
    this._value = '';
    this.button.addEventListener('click', (event) => {
      event.stopPropagation();
      this.toggle();
    });
    this.button.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      if (this.menu.hidden) this.toggle();
      this.menu.querySelector('[aria-selected="true"]')?.focus();
    });
    this.menu.addEventListener('keydown', (event) => {
      const options = [...this.menu.querySelectorAll('.dropdown-option')];
      const index = options.indexOf(document.activeElement);
      let next = index;
      if (event.key === 'ArrowDown') next = Math.min(options.length - 1, index + 1);
      else if (event.key === 'ArrowUp') next = Math.max(0, index - 1);
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = options.length - 1;
      else if (event.key === 'Escape') { event.preventDefault(); this.close(); this.button.focus(); return; }
      else return;
      event.preventDefault(); options[next]?.focus();
    });
  }

  get value() { return this._value; }

  setOptions(items) {
    this.items = items;
    this.menu.replaceChildren();
    const allItems = [{ value: '', label: this.placeholder }, ...items];
    for (const item of allItems) {
      const option = document.createElement('button');
      option.type = 'button';
      option.className = 'dropdown-option';
      option.role = 'option';
      option.dataset.value = item.value;
      option.textContent = item.label;
      option.addEventListener('click', () => {
        this.setValue(item.value, true);
        this.close();
      });
      this.menu.append(option);
    }
    if (!allItems.some((item) => item.value === this._value)) this._value = '';
    this.renderSelection();
  }

  setValue(value, emit = false) {
    const next = this.items.some((item) => item.value === value) ? value : '';
    const changed = next !== this._value;
    this._value = next;
    this.renderSelection();
    if (emit && changed && this.onChange) this.onChange(next);
  }

  renderSelection() {
    const selected = this.items.find((item) => item.value === this._value);
    this.label.textContent = selected ? selected.label : this.placeholder;
    this.menu.querySelectorAll('.dropdown-option').forEach((option) => {
      option.setAttribute('aria-selected', String(option.dataset.value === this._value));
    });
  }

  toggle() {
    const open = !this.root.classList.contains('open');
    document.querySelectorAll('.dropdown.open').forEach((node) => {
      if (node !== this.root) {
        node.classList.remove('open');
        node.querySelector('.dropdown-menu').hidden = true;
        node.querySelector('.dropdown-toggle').setAttribute('aria-expanded', 'false');
      }
    });
    this.root.classList.toggle('open', open);
    this.menu.hidden = !open;
    this.button.setAttribute('aria-expanded', String(open));
  }

  close() {
    this.root.classList.remove('open');
    this.menu.hidden = true;
    this.button.setAttribute('aria-expanded', 'false');
  }
}

const editor = CodeMirror.fromTextArea($('#editor'), {
  mode: 'stex',
  theme: 'material-darker',
  lineNumbers: true,
  lineWrapping: false,
  indentUnit: 2,
  tabSize: 2,
  autofocus: true,
  extraKeys: { 'Ctrl-S': () => saveCurrent(), 'Cmd-S': () => saveCurrent() },
});
OLeafUI.init({ editor });

const projectDropdown = new OLeafDropdown($('#project-dropdown'), (value) => {
  (value ? activateProject(value) : selectProject(value)).catch((error) => reportError(error, 'Výběr projektu'));
});
const pluginDropdown = new OLeafDropdown($('#plugin-dropdown'), () => {
  $('#apply-plugin').disabled = !state.project || !pluginDropdown.value;
});

document.addEventListener('click', () => {
  projectDropdown.close();
  pluginDropdown.close();
});

const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
const zoomStep = (value) => Math.round(value / 10) * 10;

function persistAppearanceSoon() {
  clearTimeout(state.appearanceSaveTimer);
  state.appearanceSaveTimer = setTimeout(() => {
    localStorage.setItem('oleafAppearance', JSON.stringify(state.appearance));
  }, 120);
}

function renderEditorZoom(anchor = null) {
  const next = clamp(Number(state.appearance.editorZoom) || 100, 50, 250);
  const root = document.documentElement;
  const previous = Number(root.dataset.editorZoom) || next;
  const scroller = editor.getScrollerElement();
  const info = editor.getScrollInfo();
  const rect = scroller.getBoundingClientRect();
  const localX = anchor ? clamp(anchor.clientX - rect.left, 0, rect.width) : rect.width / 2;
  const localY = anchor ? clamp(anchor.clientY - rect.top, 0, rect.height) : rect.height / 2;
  const contentX = info.left + localX;
  const contentY = info.top + localY;
  const ratio = next / previous;

  state.appearance.editorZoom = next;
  root.dataset.editorZoom = String(next);
  root.style.setProperty('--editor-font-size', `${state.appearance.fontSize * next / 100}px`);
  elements.editorZoomLabel.textContent = `${next} %`;
  $('#editor-zoom-out').disabled = next <= 50;
  $('#editor-zoom-in').disabled = next >= 250;
  requestAnimationFrame(() => {
    editor.refresh();
    if (previous !== next) editor.scrollTo((contentX * ratio) - localX, (contentY * ratio) - localY);
  });
}

function setEditorZoom(value, anchor = null) {
  state.appearance.editorZoom = clamp(zoomStep(Number(value) || 100), 50, 250);
  renderEditorZoom(anchor);
  persistAppearanceSoon();
}

function renderPdfZoom(anchor = null) {
  const next = clamp(Number(state.appearance.pdfZoom) || 100, 30, 300);
  const previous = Number(document.documentElement.dataset.pdfZoom) || next;
  const renderer = elements.pdfRenderer;
  const rect = renderer.getBoundingClientRect();
  const localX = anchor ? clamp(anchor.clientX - rect.left, 0, rect.width) : rect.width / 2;
  const localY = anchor ? clamp(anchor.clientY - rect.top, 0, rect.height) : rect.height / 2;
  const contentX = renderer.scrollLeft + localX;
  const contentY = renderer.scrollTop + localY;
  const ratio = next / previous;

  state.appearance.pdfZoom = next;
  document.documentElement.dataset.pdfZoom = String(next);
  document.documentElement.style.setProperty('--pdf-zoom', String(next / 100));
  elements.pdfZoomLabel.textContent = `${next} %`;
  $('#pdf-zoom-out').disabled = next <= 30;
  $('#pdf-zoom-in').disabled = next >= 300;
  requestAnimationFrame(() => {
    if (previous !== next) {
      renderer.scrollLeft = (contentX * ratio) - localX;
      renderer.scrollTop = (contentY * ratio) - localY;
    }
  });
}

function setPdfZoom(value, anchor = null) {
  state.appearance.pdfZoom = clamp(zoomStep(Number(value) || 100), 30, 300);
  renderPdfZoom(anchor);
  persistAppearanceSoon();
}

function bindZoomGestures(element, readZoom, writeZoom) {
  element.addEventListener('wheel', (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    const direction = event.deltaY < 0 ? 10 : -10;
    writeZoom(readZoom() + direction, event);
  }, { passive: false });

  let pinchDistance = 0;
  let pinchZoom = 100;
  const distance = (touches) => Math.hypot(
    touches[0].clientX - touches[1].clientX,
    touches[0].clientY - touches[1].clientY,
  );
  const center = (touches) => ({
    clientX: (touches[0].clientX + touches[1].clientX) / 2,
    clientY: (touches[0].clientY + touches[1].clientY) / 2,
  });

  element.addEventListener('touchstart', (event) => {
    if (event.touches.length !== 2) return;
    pinchDistance = distance(event.touches);
    pinchZoom = readZoom();
  }, { passive: true });
  element.addEventListener('touchmove', (event) => {
    if (event.touches.length !== 2 || pinchDistance <= 0) return;
    event.preventDefault();
    writeZoom(pinchZoom * distance(event.touches) / pinchDistance, center(event.touches));
  }, { passive: false });
  const endPinch = (event) => {
    if (event.touches.length < 2) pinchDistance = 0;
  };
  element.addEventListener('touchend', endPinch, { passive: true });
  element.addEventListener('touchcancel', endPinch, { passive: true });
}

function enablePointerDragScroll(element) {
  let pointerId = null;
  let startY = 0;
  let startScrollTop = 0;
  let moved = false;
  let suppressClick = false;

  element.addEventListener('pointerdown', (event) => {
    if (!event.isPrimary || event.button !== 0) return;
    if (event.target.closest('button, input, dialog, .dropdown-menu')) return;
    pointerId = event.pointerId;
    startY = event.clientY;
    startScrollTop = element.scrollTop;
    moved = false;
  });

  element.addEventListener('pointermove', (event) => {
    if (event.pointerId !== pointerId) return;
    const distance = event.clientY - startY;
    if (!moved && Math.abs(distance) < 4) return;
    if (!moved) {
      moved = true;
      element.setPointerCapture(pointerId);
    }
    event.preventDefault();
    element.classList.add('drag-scrolling');
    element.scrollTop = startScrollTop - distance;
  });

  const finish = (event) => {
    if (event.pointerId !== pointerId) return;
    if (moved) suppressClick = true;
    element.classList.remove('drag-scrolling');
    if (element.hasPointerCapture(pointerId)) element.releasePointerCapture(pointerId);
    pointerId = null;
  };
  element.addEventListener('pointerup', finish);
  element.addEventListener('pointercancel', finish);
  element.addEventListener('click', (event) => {
    if (!suppressClick) return;
    suppressClick = false;
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);
}

enablePointerDragScroll($('.sidebar'));

function enablePanDragScroll(element) {
  let pointerId = null;
  let startX = 0;
  let startY = 0;
  let startLeft = 0;
  let startTop = 0;
  let moved = false;
  let suppressClick = false;

  element.addEventListener('pointerdown', (event) => {
    if (!event.isPrimary || event.button !== 0 || event.pointerType === 'touch') return;
    pointerId = event.pointerId;
    startX = event.clientX;
    startY = event.clientY;
    startLeft = element.scrollLeft;
    startTop = element.scrollTop;
    moved = false;
  });
  element.addEventListener('pointermove', (event) => {
    if (event.pointerId !== pointerId) return;
    const deltaX = event.clientX - startX;
    const deltaY = event.clientY - startY;
    if (!moved && Math.hypot(deltaX, deltaY) < 4) return;
    if (!moved) {
      moved = true;
      element.setPointerCapture(pointerId);
      element.classList.add('drag-scrolling');
    }
    event.preventDefault();
    element.scrollLeft = startLeft - deltaX;
    element.scrollTop = startTop - deltaY;
  });
  const stop = (event) => {
    if (event.pointerId !== pointerId) return;
    if (moved) suppressClick = true;
    element.classList.remove('drag-scrolling');
    if (element.hasPointerCapture(pointerId)) element.releasePointerCapture(pointerId);
    pointerId = null;
  };
  element.addEventListener('pointerup', stop);
  element.addEventListener('pointercancel', stop);
  element.addEventListener('click', (event) => {
    if (!suppressClick) return;
    suppressClick = false;
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);
}

enablePanDragScroll(elements.pdfRenderer);

function enablePersistentSidebarScrollbar(element, rail) {
  const thumb = $('.sidebar-scrollbar-thumb', rail);
  let dragPointer = null;
  let dragStartY = 0;
  let dragStartScroll = 0;

  const geometry = () => {
    const trackHeight = Math.max(40, rail.clientHeight - 2);
    const maximum = Math.max(0, element.scrollHeight - element.clientHeight);
    const thumbHeight = maximum === 0
      ? trackHeight
      : Math.max(34, Math.round(trackHeight * element.clientHeight / element.scrollHeight));
    return { trackHeight, maximum, thumbHeight, travel: Math.max(0, trackHeight - thumbHeight) };
  };

  const sync = () => {
    const rect = element.getBoundingClientRect();
    rail.style.top = `${Math.round(rect.top + 5)}px`;
    rail.style.left = `${Math.round(rect.right - 14)}px`;
    rail.style.height = `${Math.max(40, Math.round(rect.height - 10))}px`;
    const { maximum, thumbHeight, travel } = geometry();
    thumb.style.height = `${thumbHeight}px`;
    const offset = maximum === 0 ? 0 : (element.scrollTop / maximum) * travel;
    thumb.style.transform = `translateY(${Math.round(offset)}px)`;
    rail.classList.toggle('scrollable', maximum > 0);
  };

  rail.addEventListener('pointerdown', (event) => {
    if (!event.isPrimary || event.button !== 0) return;
    event.preventDefault();
    const { maximum, thumbHeight, travel } = geometry();
    if (!event.target.closest('.sidebar-scrollbar-thumb')) {
      const rect = rail.getBoundingClientRect();
      const requested = event.clientY - rect.top - (thumbHeight / 2);
      element.scrollTop = travel === 0 ? 0 : (Math.max(0, Math.min(travel, requested)) / travel) * maximum;
    }
    dragPointer = event.pointerId;
    dragStartY = event.clientY;
    dragStartScroll = element.scrollTop;
    rail.setPointerCapture(dragPointer);
    rail.classList.add('dragging');
    sync();
  });

  rail.addEventListener('pointermove', (event) => {
    if (event.pointerId !== dragPointer) return;
    event.preventDefault();
    const { maximum, travel } = geometry();
    element.scrollTop = dragStartScroll + (travel === 0 ? 0 : (event.clientY - dragStartY) * maximum / travel);
  });

  const stopDrag = (event) => {
    if (event.pointerId !== dragPointer) return;
    rail.classList.remove('dragging');
    if (rail.hasPointerCapture(dragPointer)) rail.releasePointerCapture(dragPointer);
    dragPointer = null;
  };
  rail.addEventListener('pointerup', stopDrag);
  rail.addEventListener('pointercancel', stopDrag);
  element.addEventListener('scroll', sync, { passive: true });
  window.addEventListener('resize', sync, { passive: true });
  new ResizeObserver(sync).observe(element);
  new MutationObserver(sync).observe(element, { childList: true, subtree: true });
  requestAnimationFrame(sync);
}

enablePersistentSidebarScrollbar($('.sidebar'), $('#sidebar-scrollbar'));

function showMobilePreview(show) {
  OLeafUI.showMobilePreview(show);
}

function relativeUrl(part) {
  const pathname = window.location.pathname.endsWith('/') ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(part.replace(/^\//, ''), `${window.location.origin}${pathname}`).toString();
}

function timestamp() {
  return new Intl.DateTimeFormat('cs-CZ', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3,
  }).format(new Date());
}

function appendConsole(text, { raw = false } = {}) {
  if (!text) return;
  const wasNearBottom = elements.debugConsole.scrollHeight - elements.debugConsole.scrollTop - elements.debugConsole.clientHeight < 50;
  state.consoleBuffer += raw ? text : `[${timestamp()}] ${text}\n`;
  if (state.consoleBuffer.length > 2_500_000) {
    state.consoleBuffer = `[O-Leaf] Začátek konzole byl zkrácen kvůli velikosti.\n${state.consoleBuffer.slice(-2_400_000)}`;
  }
  elements.debugConsole.textContent = state.consoleBuffer;
  if (wasNearBottom || raw) elements.debugConsole.scrollTop = elements.debugConsole.scrollHeight;
}

function debug(message) { appendConsole(`APP  ${message}`); }

function setConsoleStatus(status, summary) {
  elements.consoleIndicator.className = `console-indicator${status ? ` ${status}` : ''}`;
  elements.consoleSummary.textContent = summary;
}

async function api(part, options = {}, quiet = false) {
  const started = performance.now();
  const method = options.method || 'GET';
  if (!quiet) debug(`${method} ${part.split('?')[0]}`);
  const response = await fetch(relativeUrl(part), {
    credentials: 'same-origin',
    cache: 'no-store',
    ...options,
    headers: options.body instanceof FormData ? options.headers : { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const contentType = response.headers.get('content-type') || '';
  const body = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!quiet) debug(`${response.status} ${method} ${part.split('?')[0]} (${Math.round(performance.now() - started)} ms)`);
  if (!response.ok) {
    const error = new Error(body.error || (typeof body === 'string' ? body : `HTTP ${response.status}`));
    error.data = body;
    error.status = response.status;
    throw error;
  }
  return body;
}

function reportError(error, context = 'Chyba') {
  appendConsole(`ERROR ${context}: ${error.stack || error.message}`);
  setConsoleStatus('error', context);
  toast(error.message, true);
}

function toast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle('error', error);
  elements.toast.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { elements.toast.hidden = true; }, 4200);
}

function setDirty(value) {
  state.dirty = value;
  elements.dirtyDot.hidden = !value;
  elements.saveState.textContent = value ? 'Neuloženo' : 'Uloženo';
}

function enableProjectActions(enabled) {
  $('#export-project').disabled = !enabled;
  $('#new-file').disabled = !enabled;
  $('#new-folder').disabled = !enabled;
  $('#compile').disabled = !enabled || Boolean(state.compileJobId);
  $('#apply-plugin').disabled = !enabled || !pluginDropdown.value;
}

async function loadSession() {
  state.session = await api('api/session');
  elements.workspaceBadge.textContent = state.session.authenticated ? state.session.user.username : 'Host';
  elements.accountButton.textContent = state.session.authenticated ? 'Odhlásit' : 'Přihlásit';
  debug(`Pracovní prostor: ${state.session.authenticated ? `uživatel ${state.session.user.username}` : 'guest'}`);
}

async function loadProjects(selectId = null) {
  state.projects = await api('api/projects');
  projectDropdown.setOptions(state.projects.map((project) => ({ value: project.id, label: project.name })));
  const target = selectId || (state.project && state.projects.some((item) => item.id === state.project.id) ? state.project.id : '');
  projectDropdown.setValue(target);
  if (target) await selectProject(target);
  else clearProject();
}

async function loadPlugins() {
  state.plugins = await api('api/plugins');
  pluginDropdown.setOptions(state.plugins.map((plugin) => ({ value: plugin.id, label: `${plugin.name} (${plugin.version})` })));
  $('#apply-plugin').disabled = !state.project || !pluginDropdown.value;
}

function clearProject() {
  state.project = null;
  $('#editor-welcome').hidden = false;
  editor.getWrapperElement().hidden = true;
  $('#header-project').textContent = 'Váš prostor pro psaní.';
  $('#project-location').textContent = 'Soukromé projekty i složky z Home Assistantu.';
  state.projectTree = [];
  state.pinnedFiles = [];
  state.file = null;
  state.fileKind = null;
  state.fileMime = null;
  clearFilePreview();
  editor.setValue('');
  editor.setOption('readOnly', true);
  elements.currentPath.textContent = 'Žádný otevřený soubor';
  elements.fileTree.className = 'file-tree empty-state';
  elements.fileTree.textContent = 'Otevřete složku nebo vytvořte nový projekt.';
  elements.pinnedSection.hidden = true;
  elements.pinnedFiles.className = 'pinned-files empty-state';
  elements.pinnedFiles.textContent = 'Zatím není nic připnuto.';
  $('#save-file').disabled = true;
  $('#delete-file').disabled = true;
  enableProjectActions(false);
  hidePdf();
  editor.getWrapperElement().hidden = true;
}

async function selectProject(projectId) {
  if (state.dirty) await saveCurrent();
  state.openFileRequest += 1;
  state.project = state.projects.find((project) => project.id === projectId) || null;
  projectDropdown.setValue(projectId);
  state.projectTree = [];
  state.pinnedFiles = [];
  state.file = null;
  state.fileKind = null;
  state.fileMime = null;
  clearFilePreview();
  state.collapsedDirs.clear();
  editor.setValue('');
  editor.setOption('readOnly', true);
  elements.currentPath.textContent = state.project ? 'Vyberte soubor' : 'Žádný otevřený soubor';
  $('#save-file').disabled = true;
  $('#delete-file').disabled = true;
  enableProjectActions(Boolean(state.project));
  hidePdf();
  $('#file-search').value = '';
  if (state.project) {
    $('#editor-welcome').hidden = true;
    editor.getWrapperElement().hidden = false;
    $('#header-project').textContent = state.project.name;
    $('#project-location').textContent = state.project.externalPath || 'Soukromý prostor addonu';
    debug(`Otevřen projekt: ${state.project.name} (${state.project.id})`);
    await loadTree();
  } else clearProject();
}

async function loadTree() {
  if (!state.project) return;
  const projectId = state.project.id;
  const [tree, pins] = await Promise.all([
    api(`api/projects/${state.project.id}/tree`),
    api(`api/projects/${state.project.id}/pins`),
  ]);
  if (state.project?.id !== projectId) return;
  state.projectTree = tree;
  state.pinnedFiles = pins.paths;
  elements.fileTree.className = 'file-tree';
  elements.fileTree.replaceChildren(renderTree(tree, true));
  if (!tree.length) {
    elements.fileTree.className = 'file-tree empty-state';
    elements.fileTree.textContent = 'Projekt zatím neobsahuje žádné soubory.';
  }
  const texFiles = [];
  const visit = (nodes) => nodes.forEach((node) => node.type === 'directory' ? visit(node.children || []) : /\.tex$/i.test(node.path) && texFiles.push(node.path));
  visit(tree);
  const currentEntry = state.project.entry || elements.entryFile.value;
  elements.entryFile.replaceChildren(...texFiles.map((file) => new Option(file, file)));
  elements.entryFile.value = texFiles.includes(currentEntry) ? currentEntry : texFiles.includes('main.tex') ? 'main.tex' : texFiles[0] || '';
  $('#compile').disabled = !texFiles.length || Boolean(state.compileJobId);
  renderPinnedFiles();
  renderFilteredTree();
  syncActiveFileRows();
}

function pinIcon() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h12l-1.5 7 3.5 4H4l3.5-4L6 3Zm6 11v7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
}

function makePinButton(filePath) {
  const pinned = state.pinnedFiles.includes(filePath);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `pin-button${pinned ? ' pinned' : ''}`;
  button.innerHTML = pinIcon();
  button.title = pinned ? `Odepnout ${filePath}` : `Připnout ${filePath}`;
  button.setAttribute('aria-label', button.title);
  button.setAttribute('aria-pressed', String(pinned));
  button.addEventListener('keydown', (event) => event.stopPropagation());
  button.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    togglePinnedFile(filePath).catch((error) => reportError(error, 'Připnutí souboru'));
  });
  return button;
}

function renderPinnedFiles() {
  elements.pinnedSection.hidden = !state.project || !state.pinnedFiles.length;
  elements.pinnedFiles.replaceChildren();
  if (!state.pinnedFiles.length) {
    elements.pinnedFiles.className = 'pinned-files empty-state';
    elements.pinnedFiles.textContent = 'Zatím není nic připnuto.';
    return;
  }
  elements.pinnedFiles.className = 'pinned-files';
  for (const filePath of state.pinnedFiles) {
    const row = document.createElement('div');
    row.className = 'pinned-file-row';
    row.dataset.filePath = filePath;
    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'pinned-file-open';
    open.title = filePath;
    const icon = document.createElement('span');
    icon.className = 'tree-icon';
    icon.append(fileIcon(filePath));
    const name = document.createElement('span');
    name.className = 'pinned-file-path';
    name.textContent = filePath;
    open.append(icon, name);
    open.addEventListener('click', () => openFile(filePath));
    row.append(open, makePinButton(filePath));
    elements.pinnedFiles.append(row);
  }
}

function syncActiveFileRows() {
  document.querySelectorAll('[data-file-path]').forEach((row) => {
    row.classList.toggle('active', row.dataset.filePath === state.file);
  });
}

async function togglePinnedFile(filePath) {
  if (!state.project) return;
  const next = state.pinnedFiles.includes(filePath)
    ? state.pinnedFiles.filter((item) => item !== filePath)
    : [...state.pinnedFiles, filePath];
  const result = await api(`api/projects/${state.project.id}/pins`, {
    method: 'PUT',
    body: JSON.stringify({ paths: next }),
  });
  state.pinnedFiles = result.paths;
  elements.fileTree.replaceChildren(renderTree(state.projectTree, true));
  renderPinnedFiles();
  syncActiveFileRows();
  const pinned = state.pinnedFiles.includes(filePath);
  debug(`${pinned ? 'Připnut' : 'Odepnut'} soubor: ${filePath}`);
  toast(pinned ? 'Soubor byl připnut.' : 'Soubor byl odepnut.');
}

function renderTree(nodes, root = false) {
  const list = document.createElement('ul');
  list.className = `tree-list${root ? ' root' : ''}`;
  for (const node of nodes) {
    const item = document.createElement('li');
    const row = document.createElement('div');
    row.className = `tree-row ${node.type}`;
    row.dataset.path = node.path;
    row.tabIndex = 0;
    row.setAttribute('role', 'button');
    row.setAttribute('aria-label', node.path);
    const icon = document.createElement('span');
    icon.className = `tree-icon${node.type === 'directory' ? ' tree-folder' : ''}`;
    const name = document.createElement('span');
    name.className = 'tree-name';
    name.textContent = node.name;
    row.append(icon, name);
    item.append(row);

    if (node.type === 'directory') {
      const children = renderTree(node.children || []);
      const collapsed = state.collapsedDirs.has(node.path);
      children.classList.toggle('collapsed', collapsed);
      icon.replaceChildren(OLeafUI.icon(collapsed ? 'folder' : 'folderOpen'));
      row.setAttribute('aria-expanded', String(!collapsed));
      const toggle = () => {
        const nextCollapsed = !children.classList.contains('collapsed');
        children.classList.toggle('collapsed', nextCollapsed);
        icon.replaceChildren(OLeafUI.icon(nextCollapsed ? 'folder' : 'folderOpen'));
        row.setAttribute('aria-expanded', String(!nextCollapsed));
        if (nextCollapsed) state.collapsedDirs.add(node.path);
        else state.collapsedDirs.delete(node.path);
      };
      row.addEventListener('click', toggle);
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(); }
      });
      item.append(children);
    } else {
      icon.append(fileIcon(node.name));
      row.dataset.filePath = node.path;
      row.append(makePinButton(node.path));
      row.addEventListener('click', () => openFile(node.path));
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') openFile(node.path);
      });
    }
    list.append(item);
  }
  return list;
}

function fileIcon(name) {
  if (/\.tex$/i.test(name)) return OLeafUI.icon('editor');
  if (/\.bib$/i.test(name)) return OLeafUI.icon('bib');
  if (/\.pdf$/i.test(name)) return OLeafUI.icon('pdf');
  if (/\.(png|jpe?g|gif|webp|bmp|ico|avif|svg)$/i.test(name)) return OLeafUI.icon('image');
  return OLeafUI.icon('file');
}

function formatBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return `${value} B`;
  const units = ['kB', 'MB', 'GB'];
  let scaled = value / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && scaled >= 1024; index += 1) {
    scaled /= 1024;
    unit = units[index];
  }
  return `${new Intl.NumberFormat('cs-CZ', { maximumFractionDigits: scaled < 10 ? 2 : 1 }).format(scaled)} ${unit}`;
}

function rawFileUrl(filePath, download = false) {
  const query = new URLSearchParams({ path: filePath });
  if (download) query.set('download', '1');
  return relativeUrl(`api/projects/${state.project.id}/file/raw?${query}`);
}

function clearFilePreview() {
  state.filePreviewToken += 1;
  elements.filePreview.querySelectorAll('audio, video').forEach((media) => {
    media.pause();
    media.removeAttribute('src');
    media.load();
  });
  elements.filePreview.replaceChildren();
  elements.filePreview.hidden = true;
  editor.getWrapperElement().hidden = false;
  $('#editor-pane').classList.remove('previewing');
}

function showFilePreview() {
  editor.getWrapperElement().hidden = true;
  elements.filePreview.hidden = false;
  $('#editor-pane').classList.add('previewing');
}

function previewToolbar(file, label) {
  const toolbar = document.createElement('div');
  toolbar.className = 'file-preview-toolbar';
  const summary = document.createElement('div');
  summary.className = 'file-preview-summary';
  const kind = document.createElement('strong');
  kind.textContent = label;
  const meta = document.createElement('span');
  meta.textContent = `${formatBytes(file.bytes)} · ${file.mime || 'application/octet-stream'}`;
  const download = document.createElement('a');
  download.className = 'button small file-download';
  download.href = rawFileUrl(file.path, true);
  download.textContent = 'Stáhnout';
  download.title = `Stáhnout ${file.path}`;
  summary.append(kind, meta);
  toolbar.append(summary, download);
  return toolbar;
}

function mediaErrorMessage(message) {
  const note = document.createElement('p');
  note.className = 'file-preview-error';
  note.textContent = message;
  return note;
}

async function renderFilePreview(file) {
  clearFilePreview();
  const token = state.filePreviewToken;
  showFilePreview();

  if (file.kind === 'pdf') {
    elements.filePreview.append(previewToolbar(file, 'PDF dokument'));
    const renderer = document.createElement('div');
    renderer.className = 'source-pdf-renderer';
    renderer.tabIndex = 0;
    renderer.setAttribute('aria-label', `Náhled ${file.path}`);
    const waiting = mediaErrorMessage('Zjišťuji počet stran PDF…');
    renderer.append(waiting);
    elements.filePreview.append(renderer);
    try {
      const info = await api(`api/projects/${state.project.id}/file/pdf/info?path=${encodeURIComponent(file.path)}`, {}, true);
      if (token !== state.filePreviewToken) return;
      renderer.replaceChildren();
      const pages = document.createElement('div');
      pages.className = 'source-pdf-pages';
      for (let page = 1; page <= info.pages; page += 1) {
        const card = document.createElement('article');
        card.className = 'source-pdf-page';
        card.dataset.state = 'loading';
        const badge = document.createElement('span');
        badge.className = 'source-pdf-page-badge';
        badge.textContent = `${page} / ${info.pages}`;
        const status = document.createElement('span');
        status.className = 'source-pdf-page-status';
        status.textContent = `Načítám stranu ${page}…`;
        const image = document.createElement('img');
        image.alt = `Strana ${page} souboru ${file.path}`;
        image.loading = page <= 2 ? 'eager' : 'lazy';
        image.decoding = 'async';
        image.addEventListener('load', () => { card.dataset.state = 'loaded'; });
        image.addEventListener('error', () => {
          card.dataset.state = 'error';
          status.textContent = `Stranu ${page} se nepodařilo vykreslit.`;
        });
        image.src = relativeUrl(`api/projects/${state.project.id}/file/pdf/page/${page}?path=${encodeURIComponent(file.path)}&v=${encodeURIComponent(info.version)}`);
        card.append(image, badge, status);
        pages.append(card);
      }
      renderer.append(pages);
      debug(`Náhled PDF: ${file.path} (${info.pages} stran)`);
    } catch (error) {
      if (token !== state.filePreviewToken) return;
      renderer.replaceChildren(mediaErrorMessage(`PDF nelze zobrazit: ${error.message}`));
      reportError(error, 'Náhled PDF souboru');
    }
    return;
  }

  if (file.kind === 'image') {
    elements.filePreview.append(previewToolbar(file, 'Obrázek'));
    const stage = document.createElement('div');
    stage.className = 'file-media-stage image-stage';
    const image = document.createElement('img');
    image.className = 'file-image-preview';
    image.alt = file.path;
    image.src = rawFileUrl(file.path);
    image.addEventListener('error', () => stage.append(mediaErrorMessage('Obrázek se nepodařilo zobrazit.')));
    stage.append(image);
    elements.filePreview.append(stage);
    return;
  }

  if (file.kind === 'audio' || file.kind === 'video') {
    const video = file.kind === 'video';
    elements.filePreview.append(previewToolbar(file, video ? 'Video' : 'Zvuk'));
    const stage = document.createElement('div');
    stage.className = `file-media-stage ${video ? 'video-stage' : 'audio-stage'}`;
    const media = document.createElement(video ? 'video' : 'audio');
    media.className = 'file-media-preview';
    media.controls = true;
    media.preload = 'metadata';
    media.src = rawFileUrl(file.path);
    media.addEventListener('error', () => stage.append(mediaErrorMessage('Prohlížeč tento mediální soubor nedokáže přehrát.')));
    stage.append(media);
    elements.filePreview.append(stage);
    return;
  }

  elements.filePreview.append(previewToolbar(file, 'Binární soubor'));
  const card = document.createElement('section');
  card.className = 'binary-preview-card';
  const mark = document.createElement('div');
  mark.className = 'binary-preview-mark';
  mark.textContent = '0101';
  const title = document.createElement('h3');
  title.textContent = 'Tento soubor není textový';
  const description = document.createElement('p');
  description.textContent = 'O-Leaf ho ponechává beze změny. Níže je bezpečný náhled prvních bajtů; celý soubor lze stáhnout.';
  const hex = document.createElement('pre');
  hex.className = 'binary-hex';
  hex.textContent = file.hex || 'Soubor je prázdný.';
  card.append(mark, title, description, hex);
  elements.filePreview.append(card);
}

async function openFile(filePath) {
  const request = ++state.openFileRequest;
  const projectId = state.project?.id;
  if (!projectId) return false;
  try {
    if (state.dirty) await saveCurrent();
    const file = await api(`api/projects/${projectId}/file?path=${encodeURIComponent(filePath)}`);
    if (request !== state.openFileRequest || state.project?.id !== projectId) return false;
    clearSourceHighlight();
    state.loadingFile = true;
    state.file = file.path;
    state.fileKind = file.kind;
    state.fileMime = file.mime;
    editor.setValue('');
    editor.clearHistory();
    elements.currentPath.textContent = file.path;
    $('#delete-file').disabled = false;
    if (file.kind === 'text') {
      clearFilePreview();
      editor.setOption('mode', /\.(tex|bib|sty|cls|dtx)$/i.test(file.path) ? 'stex' : null);
      editor.setOption('readOnly', false);
      editor.setValue(file.content || '');
      editor.clearHistory();
      $('#save-file').disabled = false;
    } else {
      editor.setOption('readOnly', true);
      $('#save-file').disabled = true;
      await renderFilePreview(file);
    }
    syncActiveFileRows();
    setDirty(false);
    debug(`Otevřen soubor: ${file.path} (${file.kind}, ${formatBytes(file.bytes)})`);
    if (file.kind === 'text') editor.focus();
    return true;
  } catch (error) {
    reportError(error, 'Otevření souboru');
    return false;
  } finally {
    state.loadingFile = false;
  }
}

async function saveCurrent() {
  if (state.savePromise) { await state.savePromise; return saveCurrent(); }
  if (!state.project || !state.file || state.fileKind !== 'text' || !state.dirty) return;
  state.saving = true;
  const projectId = state.project.id;
  const filePath = state.file;
  const content = editor.getValue();
  elements.saveState.textContent = 'Ukládám…';
  state.savePromise = api(`api/projects/${projectId}/file`, {
    method: 'PUT',
    body: JSON.stringify({ path: filePath, content }),
  });
  try {
    await state.savePromise;
    if (state.project?.id === projectId && state.file === filePath && editor.getValue() === content) setDirty(false);
  } catch (error) {
    elements.saveState.textContent = 'Chyba ukládání';
    reportError(error, 'Ukládání souboru');
    throw error;
  } finally {
    state.saving = false;
    state.savePromise = null;
  }
  if (state.dirty) return saveCurrent();
}

editor.on('change', () => {
  if (!state.file || state.fileKind !== 'text' || state.loadingFile) return;
  setDirty(true);
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => saveCurrent().catch(() => {}), state.session?.options?.autosaveDelayMs || 800);
});
editor.getWrapperElement().addEventListener('click', (event) => {
  if (event.target.closest('.CodeMirror-vscrollbar, .CodeMirror-hscrollbar')) return;
  setTimeout(() => syncEditorToPdf(), 0);
});

function releasePdf() {
  if (state.pdfObjectUrl) URL.revokeObjectURL(state.pdfObjectUrl);
  state.pdfObjectUrl = null;
  state.pdfDirectUrl = null;
  state.pdfBlob = null;
}

function clearPdfRenderer() {
  state.pdfLoadToken += 1;
  state.pdfObserver?.disconnect();
  state.pdfObserver = null;
  if (state.pdfScrollFrame) cancelAnimationFrame(state.pdfScrollFrame);
  state.pdfScrollFrame = null;
  elements.pdfPages.replaceChildren();
}

function hidePdf() {
  releasePdf();
  clearPdfRenderer();
  state.pdfPage = 0;
  state.pdfPages = 0;
  elements.pdfRenderer.hidden = true;
  elements.pdfRenderer.classList.remove('loading');
  elements.pdfPageLabel.textContent = '– / –';
  elements.pdfPrev.disabled = true;
  elements.pdfNext.disabled = true;
  elements.previewPlaceholder.hidden = false;
  elements.openPdf.disabled = true;
  elements.downloadPdf.disabled = true;
  showMobilePreview(false);
}

function pdfPageNode(page) {
  return elements.pdfPages.querySelector(`.pdf-page[data-page="${page}"]`);
}

function setCurrentPdfPage(page) {
  if (!state.pdfPages) return;
  const selected = clamp(Number(page) || 1, 1, state.pdfPages);
  state.pdfPage = selected;
  elements.pdfPageLabel.textContent = `${selected} / ${state.pdfPages}`;
  elements.pdfPrev.disabled = selected <= 1;
  elements.pdfNext.disabled = selected >= state.pdfPages;
  elements.pdfPages.querySelectorAll('.pdf-page.current').forEach((node) => node.classList.remove('current'));
  pdfPageNode(selected)?.classList.add('current');
}

function pdfPageUrl(page) {
  const entry = elements.entryFile.value.trim() || 'main.tex';
  return relativeUrl(`api/projects/${state.project.id}/pdf/page/${page}?entry=${encodeURIComponent(entry)}&v=${state.pdfRevision}`);
}

function sizePdfPage(node, image) {
  if (!elements.pdfRenderer.clientWidth) return;
  const style = getComputedStyle(elements.pdfRenderer);
  const availableWidth = Math.max(64, elements.pdfRenderer.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight));
  const baseWidth = Math.min(image.naturalWidth || 1050, availableWidth, 1050);
  const aspect = image.naturalWidth ? image.naturalHeight / image.naturalWidth : Math.SQRT2;
  node.style.setProperty('--pdf-page-width', `${baseWidth}px`);
  node.style.setProperty('--pdf-page-height', `${baseWidth * aspect}px`);
}

function loadPdfPage(page) {
  const node = pdfPageNode(page);
  if (!node || node.dataset.state === 'loaded') return Promise.resolve();
  if (node._loadPromise) return node._loadPromise;
  const token = state.pdfLoadToken;
  const image = node.querySelector('img');
  const status = node.querySelector('.pdf-page-status');
  node.dataset.state = 'loading';
  status.textContent = `Načítám stranu ${page}…`;

  node._loadPromise = new Promise((resolve, reject) => {
    image.onload = () => {
      if (token !== state.pdfLoadToken) return resolve();
      sizePdfPage(node, image);
      node.dataset.state = 'loaded';
      status.textContent = '';
      node._loadPromise = null;
      resolve();
    };
    image.onerror = () => {
      if (token !== state.pdfLoadToken) return resolve();
      node.dataset.state = 'error';
      status.textContent = `Stranu ${page} se nepodařilo načíst. Klikněte pro opakování.`;
      node._loadPromise = null;
      reject(new Error(`Nepodařilo se vykreslit stranu ${page}.`));
    };
    image.src = pdfPageUrl(page);
  });
  return node._loadPromise;
}

function loadPdfPageAndNeighbours(page) {
  for (let candidate = Math.max(1, page - 1); candidate <= Math.min(state.pdfPages, page + 2); candidate += 1) {
    loadPdfPage(candidate).catch((error) => debug(`PDF strana ${candidate}: ${error.message}`));
  }
}

function updatePdfPageFromScroll() {
  state.pdfScrollFrame = null;
  if (!state.pdfPages) return;
  const probe = elements.pdfRenderer.scrollTop + Math.max(40, elements.pdfRenderer.clientHeight * 0.28);
  let current = 1;
  for (const node of elements.pdfPages.querySelectorAll('.pdf-page')) {
    if (node.offsetTop <= probe) current = Number(node.dataset.page);
    else break;
  }
  setCurrentPdfPage(current);
  loadPdfPageAndNeighbours(current);
}

function showPdfPage(page, behavior = 'smooth') {
  if (!state.project || !state.pdfPages) return;
  const selected = clamp(Number(page) || 1, 1, state.pdfPages);
  const node = pdfPageNode(selected);
  if (!node) return;
  loadPdfPageAndNeighbours(selected);
  setCurrentPdfPage(selected);
  elements.pdfRenderer.scrollTo({ top: Math.max(0, node.offsetTop - 12), behavior });
}

function setSyncBusy(busy) {
  document.body.classList.toggle('synctex-busy', busy);
  document.querySelectorAll('.synctex-hint').forEach((hint) => hint.setAttribute('aria-busy', String(busy)));
}

function clearSourceHighlight() {
  if (state.syncLineHandle) editor.removeLineClass(state.syncLineHandle, 'background', 'synctex-source-line');
  clearTimeout(state.syncLineTimer);
  state.syncLineHandle = null;
}

function highlightSourceLocation(line, column = 0) {
  clearSourceHighlight();
  const lineIndex = clamp((Number(line) || 1) - 1, 0, Math.max(0, editor.lineCount() - 1));
  const lineLength = editor.getLine(lineIndex)?.length || 0;
  const position = { line: lineIndex, ch: clamp(Number(column) || 0, 0, lineLength) };
  editor.operation(() => {
    editor.setCursor(position);
    editor.scrollIntoView({ from: position, to: position }, 90);
    state.syncLineHandle = editor.addLineClass(lineIndex, 'background', 'synctex-source-line');
  });
  editor.focus();
  state.syncLineTimer = setTimeout(() => {
    clearSourceHighlight();
  }, 4500);
}

async function showPdfLocation(result) {
  showMobilePreview(true);
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const node = pdfPageNode(result.page);
  if (!node) throw new Error(`Strana ${result.page} v PDF neexistuje.`);
  await loadPdfPage(result.page);
  const image = node.querySelector('img');
  if (!image.naturalWidth || !image.naturalHeight) throw new Error('Stranu PDF se nepodařilo zaměřit.');
  elements.pdfPages.querySelectorAll('.synctex-marker').forEach((marker) => marker.remove());
  const left = clamp((Number(result.x) * 2 / image.naturalWidth) * 100, 0, 100);
  const top = clamp((Number(result.y) * 2 / image.naturalHeight) * 100, 0, 100);
  const marker = document.createElement('span');
  marker.className = 'synctex-marker';
  marker.style.left = `${left}%`;
  marker.style.top = `${top}%`;
  marker.setAttribute('aria-label', 'Nalezené místo v PDF');
  node.append(marker);
  setCurrentPdfPage(result.page);
  const targetTop = node.offsetTop + (top / 100) * node.offsetHeight - elements.pdfRenderer.clientHeight / 2;
  elements.pdfRenderer.scrollTo({ top: Math.max(0, targetTop), behavior: 'smooth' });
  setTimeout(() => marker.classList.add('settled'), 1800);
}

async function syncEditorToPdf() {
  if (!state.project || !state.file || !state.file.toLowerCase().endsWith('.tex')) return;
  const request = ++state.syncRequest;
  const cursor = editor.getCursor();
  setSyncBusy(true);
  try {
    const result = await api(`api/projects/${state.project.id}/synctex/forward`, {
      method: 'POST',
      body: JSON.stringify({
        entry: elements.entryFile.value.trim() || 'main.tex',
        path: state.file,
        line: cursor.line + 1,
        column: cursor.ch,
      }),
    });
    if (request !== state.syncRequest) return;
    if (!state.pdfPages) await loadPdf();
    await showPdfLocation(result);
    debug(`SyncTeX zdroj → PDF: ${state.file}:${cursor.line + 1} → strana ${result.page}`);
  } catch (error) {
    if (request === state.syncRequest) reportError(error, 'Křížová navigace do PDF');
  } finally {
    if (request === state.syncRequest) setSyncBusy(false);
  }
}

async function syncPdfToEditor(event, node) {
  const image = node.querySelector('img');
  const rect = image.getBoundingClientRect();
  if (!state.project || node.dataset.state !== 'loaded' || !image.naturalWidth
      || event.clientX < rect.left || event.clientX > rect.right
      || event.clientY < rect.top || event.clientY > rect.bottom) return;
  const request = ++state.syncRequest;
  const page = Number(node.dataset.page);
  const x = ((event.clientX - rect.left) / rect.width) * image.naturalWidth / 2;
  const y = ((event.clientY - rect.top) / rect.height) * image.naturalHeight / 2;
  setSyncBusy(true);
  try {
    const result = await api(`api/projects/${state.project.id}/synctex/reverse`, {
      method: 'POST',
      body: JSON.stringify({ entry: elements.entryFile.value.trim() || 'main.tex', page, x, y }),
    });
    if (request !== state.syncRequest) return;
    if (state.file !== result.path && !(await openFile(result.path))) return;
    showMobilePreview(false);
    await new Promise((resolve) => requestAnimationFrame(resolve));
    highlightSourceLocation(result.line, result.column);
    debug(`SyncTeX PDF → zdroj: strana ${page} → ${result.path}:${result.line}`);
    toast(`${result.path}, řádek ${result.line}`);
  } catch (error) {
    if (request === state.syncRequest) reportError(error, 'Křížová navigace do zdroje');
  } finally {
    if (request === state.syncRequest) setSyncBusy(false);
  }
}

async function renderPdfPages() {
  clearPdfRenderer();
  const token = state.pdfLoadToken;
  const fragment = document.createDocumentFragment();
  const defaultWidth = Math.min(Math.max(280, elements.pdfRenderer.clientWidth - 40), 1050);
  for (let page = 1; page <= state.pdfPages; page += 1) {
    const node = document.createElement('article');
    node.className = 'pdf-page';
    node.dataset.page = String(page);
    node.dataset.state = 'waiting';
    node.style.setProperty('--pdf-page-width', `${defaultWidth}px`);
    node.style.setProperty('--pdf-page-height', `${defaultWidth * Math.SQRT2}px`);
    node.setAttribute('aria-label', `Strana PDF ${page} z ${state.pdfPages}`);

    const badge = document.createElement('span');
    badge.className = 'pdf-page-badge';
    badge.textContent = String(page);
    const status = document.createElement('span');
    status.className = 'pdf-page-status';
    status.textContent = `Strana ${page}`;
    const image = document.createElement('img');
    image.alt = `Strana ${page} z ${state.pdfPages}`;
    image.decoding = 'async';
    image.loading = page <= 2 ? 'eager' : 'lazy';
    sizePdfPage(node, image);
    node.append(badge, status, image);
    node.addEventListener('click', (event) => {
      if (node.dataset.state === 'error') {
        loadPdfPage(page).catch((error) => reportError(error, 'PDF'));
        return;
      }
      syncPdfToEditor(event, node);
    });
    fragment.append(node);
  }
  elements.pdfPages.append(fragment);
  elements.pdfRenderer.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  setCurrentPdfPage(1);

  state.pdfObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting || token !== state.pdfLoadToken) continue;
      loadPdfPageAndNeighbours(Number(entry.target.dataset.page));
    }
  }, { root: elements.pdfRenderer, rootMargin: '900px 500px', threshold: 0.01 });
  elements.pdfPages.querySelectorAll('.pdf-page').forEach((node) => state.pdfObserver.observe(node));
  loadPdfPageAndNeighbours(1);
  await loadPdfPage(1);
}

async function loadPdf() {
  if (!state.project) return;
  const entry = elements.entryFile.value.trim() || 'main.tex';
  state.pdfRevision = Date.now();
  const url = relativeUrl(`api/projects/${state.project.id}/pdf?entry=${encodeURIComponent(entry)}&v=${state.pdfRevision}`);
  debug(`Načítám PDF pro ${entry}`);
  const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
  if (!response.ok) {
    let message = `PDF server odpověděl HTTP ${response.status}.`;
    try { message = (await response.json()).error || message; } catch {}
    throw new Error(message);
  }
  const blob = await response.blob();
  const signature = await blob.slice(0, 5).text();
  if (signature !== '%PDF-') throw new Error(`Server nevrátil platné PDF (typ ${blob.type || 'neznámý'}, ${blob.size} B).`);
  releasePdf();
  state.pdfBlob = blob;
  state.pdfObjectUrl = URL.createObjectURL(blob);
  state.pdfDirectUrl = url;
  const info = await api(`api/projects/${state.project.id}/pdf/info?entry=${encodeURIComponent(entry)}&v=${state.pdfRevision}`);
  state.pdfPages = info.pages;
  state.pdfRevision = info.version || state.pdfRevision;
  elements.previewPlaceholder.hidden = true;
  elements.pdfRenderer.hidden = false;
  elements.openPdf.disabled = false;
  elements.downloadPdf.disabled = false;
  await renderPdfPages();
  showMobilePreview(true);
  debug(`PDF zobrazeno jako plynulý dokument: ${blob.size} B, počet stran ${state.pdfPages}, podpis ${signature}`);
}

function setCompileProgress(progress, phase) {
  const rounded = Math.max(0, Math.min(100, Math.round(progress || 0)));
  elements.progressWrap.hidden = false;
  document.body.classList.add('compiling');
  elements.progressBar.style.width = `${rounded}%`;
  elements.progressPercent.textContent = `${rounded} %`;
  elements.progressLabel.textContent = phase || 'Probíhá kompilace';
  elements.consoleSummary.textContent = phase || 'Kompiluji';
}

function finishCompileProgress(success, phase) {
  setCompileProgress(100, phase);
  setTimeout(() => {
    elements.progressWrap.hidden = true;
    document.body.classList.remove('compiling');
  }, success ? 2200 : 5000);
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function compile() {
  if (!state.project || state.compileJobId) return;
  const button = $('#compile');
  let logOffset = 0;
  try {
    await saveCurrent();
    hidePdf();
    state.compileCommandLogged = false;
    button.disabled = true;
    OLeafUI.setActionLabel(button, 'Kompiluji…');
    button.setAttribute('aria-busy', 'true');
    elements.saveState.textContent = 'Probíhá kompilace';
    setConsoleStatus('running', 'Spouštím kompilátor');
    setCompileProgress(1, 'Odesílám úlohu');
    appendConsole(`\n${'─'.repeat(72)}\n[${timestamp()}] COMPILE projekt=${state.project.id} entry=${elements.entryFile.value.trim() || 'main.tex'}\n`, { raw: true });

    const started = await api(`api/projects/${state.project.id}/compile/start`, {
      method: 'POST',
      body: JSON.stringify({ entry: elements.entryFile.value.trim() || 'main.tex' }),
    });
    state.compileJobId = started.jobId;

    while (state.compileJobId) {
      const status = await api(`api/compile/${state.compileJobId}/status?offset=${logOffset}`, {}, true);
      if (status.command && !state.compileCommandLogged) {
        appendConsole(`COMMAND ${status.command}`);
        state.compileCommandLogged = true;
      }
      if (status.logChunk) appendConsole(status.logChunk, { raw: true });
      logOffset = status.nextOffset;
      setCompileProgress(status.progress, status.phase);

      if (status.status === 'running') {
        await wait(450);
        continue;
      }

      const result = status.result || { ok: false, error: 'Chybí výsledek kompilace.' };
      state.compileJobId = null;
      appendConsole(`RESULT status=${status.status} exitCode=${result.exitCode ?? 'null'} duration=${result.durationMs ?? '?'}ms timedOut=${Boolean(result.timedOut)}`);
      if (!result.ok) throw new Error(result.error || (result.timedOut ? 'Kompilace překročila časový limit.' : `Kompilace skončila s kódem ${result.exitCode}.`));

      setConsoleStatus('success', `Hotovo za ${((result.durationMs || 0) / 1000).toFixed(1)} s`);
      elements.saveState.textContent = 'Načítám PDF';
      await loadPdf();
      elements.saveState.textContent = 'PDF je aktuální';
      finishCompileProgress(true, 'PDF zobrazeno');
      toast('Kompilace byla úspěšná a PDF bylo automaticky obnoveno.');
      return;
    }
  } catch (error) {
    state.compileJobId = null;
    setConsoleStatus('error', 'Kompilace selhala');
    elements.saveState.textContent = 'Kompilace selhala';
    finishCompileProgress(false, 'Kompilace selhala');
    reportError(error, 'Kompilace');
  } finally {
    button.disabled = !state.project;
    OLeafUI.setActionLabel(button, 'Kompilovat');
    button.removeAttribute('aria-busy');
  }
}

async function createNode(type) {
  if (!state.project) return;
  const isDirectory = type === 'directory';
  const parent = state.file?.includes('/') ? state.file.slice(0, state.file.lastIndexOf('/') + 1) : '';
  await actionDialog({ title: isDirectory ? 'Nová podsložka' : 'Nový soubor',
    description: 'Cesta je relativní k otevřenému projektu. Pro podsložky použijte lomítko.',
    label: 'Cesta v projektu', value: parent + (isDirectory ? 'kapitoly' : 'kapitola.tex'), submit: 'Vytvořit',
    onSubmit: async (nodePath) => {
      await api(`api/projects/${state.project.id}/node`, { method: 'POST', body: JSON.stringify({ path: nodePath, type }) });
      await loadTree();
      if (!isDirectory) await openFile(nodePath.replaceAll('\\', '/'));
      toast(isDirectory ? 'Podsložka byla vytvořena.' : 'Soubor byl vytvořen.');
      return true;
    },
  });
}

async function deleteFile() {
  if (!state.project || !state.file) return;
  if (!await actionDialog({ title: 'Smazat soubor?', description: `Soubor ${state.file} bude odstraněn${state.project.externalPath ? ' i z původní složky v Home Assistantu' : ''}.`, submit: 'Smazat soubor', onSubmit: async () => true })) return;
  try {
    await api(`api/projects/${state.project.id}/node?path=${encodeURIComponent(state.file)}`, { method: 'DELETE' });
    state.file = null;
    state.fileKind = null;
    state.fileMime = null;
    clearFilePreview();
    editor.setValue('');
    editor.setOption('readOnly', true);
    elements.currentPath.textContent = 'Vyberte soubor';
    $('#save-file').disabled = true;
    $('#delete-file').disabled = true;
    await loadTree();
  } catch (error) { reportError(error, 'Mazání souboru'); }
}

async function uploadProject(file) {
  const form = new FormData();
  form.append('file', file);
  const project = await api('api/projects/import', { method: 'POST', body: form });
  await loadProjects(project.id);
  toast('Projekt byl importován.');
}

async function uploadPlugin(file) {
  const form = new FormData();
  form.append('file', file);
  const plugin = await api('api/plugins/import', { method: 'POST', body: form });
  await loadPlugins();
  pluginDropdown.setValue(plugin.id);
  $('#apply-plugin').disabled = !state.project;
  toast(`Plugin ${plugin.name} byl nainstalován.`);
}

async function applyPlugin() {
  if (!state.project || !pluginDropdown.value) return;
  const choice = await actionDialog({ title: 'Použít plugin', description: 'Vyberte, jak naložit se soubory, které už v projektu existují.', label: 'Způsob použití', choices: [{ value: 'doplnit', label: 'Pouze doplnit chybějící soubory' }, { value: 'přepsat', label: 'Přepsat i existující soubory' }], submit: 'Použít plugin', onSubmit: async (value) => value });
  if (!choice) return;
  const overwrite = choice === 'přepsat';
  try {
    await api(`api/projects/${state.project.id}/apply-plugin`, {
      method: 'POST',
      body: JSON.stringify({ pluginId: pluginDropdown.value, overwrite }),
    });
    await loadTree();
    toast('Plugin byl použit na aktivní projekt.');
  } catch (error) { reportError(error, 'Použití pluginu'); }
}

function showAuth(mode = 'login') {
  state.authMode = mode;
  const register = mode === 'register';
  elements.authTitle.textContent = register ? 'Vytvoření účtu' : 'Přihlášení';
  elements.authDescription.textContent = register ? 'Účet dostane vlastní oddělený pracovní prostor.' : 'Po přihlášení uvidíte pouze svůj pracovní prostor.';
  elements.authSubmit.textContent = register ? 'Vytvořit účet' : 'Přihlásit';
  elements.authSwitch.textContent = register ? 'Už mám účet' : 'Vytvořit účet';
  elements.authPassword.autocomplete = register ? 'new-password' : 'current-password';
  elements.authError.hidden = true;
  if (!elements.authDialog.open) elements.authDialog.showModal();
  elements.authUsername.focus();
}

async function submitAuth(event) {
  event.preventDefault();
  elements.authError.hidden = true;
  try {
    if (state.dirty) await saveCurrent();
    await api(`api/auth/${state.authMode}`, {
      method: 'POST',
      body: JSON.stringify({ username: elements.authUsername.value, password: elements.authPassword.value }),
    });
    elements.authDialog.close();
    elements.authForm.reset();
    state.project = null;
    await loadSession();
    await loadProjects();
    toast(state.authMode === 'register' ? 'Účet byl vytvořen.' : 'Přihlášení bylo úspěšné.');
  } catch (error) {
    elements.authError.textContent = error.message;
    elements.authError.hidden = false;
    appendConsole(`AUTH ${error.message}`);
  }
}

function loadAppearance() {
  try {
    state.appearance = { ...DEFAULT_APPEARANCE, ...JSON.parse(localStorage.getItem('oleafAppearance') || '{}') };
    if (state.appearance.theme === 'forest') state.appearance.theme = 'workflow';
  } catch {
    state.appearance = { ...DEFAULT_APPEARANCE };
  }
  applyAppearance();
}

function applyAppearance() {
  const appearance = state.appearance;
  appearance.fontSize = clamp(Number(appearance.fontSize) || 14, 11, 22);
  appearance.editorZoom = clamp(Number(appearance.editorZoom) || 100, 50, 250);
  appearance.pdfZoom = clamp(Number(appearance.pdfZoom) || 100, 30, 300);
  document.documentElement.dataset.theme = appearance.theme;
  document.documentElement.style.setProperty('--console-height', `${appearance.consoleHeight}px`);
  elements.workspace.classList.toggle('console-collapsed', Boolean(appearance.consoleCollapsed));
  editor.setOption('theme', appearance.theme === 'light' ? 'default' : 'material-darker');
  editor.setOption('lineWrapping', Boolean(appearance.wordWrap));
  document.querySelectorAll('input[name="theme"]').forEach((input) => { input.checked = input.value === appearance.theme; });
  $('#font-size-setting').value = appearance.fontSize;
  $('#font-size-output').textContent = `${appearance.fontSize} px`;
  $('#word-wrap-setting').checked = Boolean(appearance.wordWrap);
  $('#console-height-setting').value = appearance.consoleHeight;
  $('#console-height-output').textContent = `${appearance.consoleHeight} px`;
  $('#toggle-console').title = appearance.consoleCollapsed ? 'Rozbalit konzoli' : 'Sbalit konzoli';
  renderEditorZoom();
  renderPdfZoom();
}

function saveAppearanceFromForm() {
  state.appearance = {
    ...state.appearance,
    theme: document.querySelector('input[name="theme"]:checked')?.value || 'workflow',
    fontSize: Number($('#font-size-setting').value),
    wordWrap: $('#word-wrap-setting').checked,
    consoleHeight: Number($('#console-height-setting').value),
  };
  localStorage.setItem('oleafAppearance', JSON.stringify(state.appearance));
  applyAppearance();
}

function toggleConsole() {
  state.appearance.consoleCollapsed = !state.appearance.consoleCollapsed;
  localStorage.setItem('oleafAppearance', JSON.stringify(state.appearance));
  applyAppearance();
}

function downloadCurrentPdf() {
  if (!state.pdfBlob) return;
  const link = document.createElement('a');
  const entry = elements.entryFile.value.trim() || 'main.tex';
  link.href = state.pdfObjectUrl;
  link.download = `${entry.replace(/\.tex$/i, '')}.pdf`;
  link.click();
}

initProjectUX();

$('#new-project').addEventListener('click', createNewProject);
$('#new-file').addEventListener('click', () => createNode('file'));
$('#new-folder').addEventListener('click', () => createNode('directory'));
$('#delete-file').addEventListener('click', deleteFile);
$('#save-file').addEventListener('click', () => saveCurrent().catch(() => {}));
$('#compile').addEventListener('click', compile);
$('#pane-toggle').addEventListener('click', () => OLeafUI.togglePane());
$('#refresh-pdf').addEventListener('click', () => loadPdf().catch((error) => reportError(error, 'Obnovení PDF')));
elements.pdfPrev.addEventListener('click', () => showPdfPage(state.pdfPage - 1));
elements.pdfNext.addEventListener('click', () => showPdfPage(state.pdfPage + 1));
$('#editor-zoom-out').addEventListener('click', () => setEditorZoom(state.appearance.editorZoom - 10));
$('#editor-zoom-in').addEventListener('click', () => setEditorZoom(state.appearance.editorZoom + 10));
$('#pdf-zoom-out').addEventListener('click', () => setPdfZoom(state.appearance.pdfZoom - 10));
$('#pdf-zoom-in').addEventListener('click', () => setPdfZoom(state.appearance.pdfZoom + 10));
bindZoomGestures(editor.getWrapperElement(), () => state.appearance.editorZoom, setEditorZoom);
bindZoomGestures(elements.pdfRenderer, () => state.appearance.pdfZoom, setPdfZoom);
elements.pdfRenderer.addEventListener('scroll', () => {
  if (state.pdfScrollFrame) return;
  state.pdfScrollFrame = requestAnimationFrame(updatePdfPageFromScroll);
}, { passive: true });
new ResizeObserver(() => {
  elements.pdfPages.querySelectorAll('.pdf-page').forEach((node) => {
    sizePdfPage(node, node.querySelector('img'));
  });
}).observe(elements.pdfRenderer);
elements.openPdf.addEventListener('click', () => { if (state.pdfDirectUrl) window.open(state.pdfDirectUrl, '_blank', 'noopener'); });
elements.downloadPdf.addEventListener('click', downloadCurrentPdf);
$('#import-project').addEventListener('click', () => elements.projectUpload.click());
$('#import-plugin').addEventListener('click', () => elements.pluginUpload.click());
$('#apply-plugin').addEventListener('click', applyPlugin);
$('#export-project').addEventListener('click', () => {
  if (state.project) window.location.href = relativeUrl(`api/projects/${state.project.id}/export`);
});
elements.projectUpload.addEventListener('change', () => {
  const [file] = elements.projectUpload.files;
  if (file) uploadProject(file).catch((error) => reportError(error, 'Import projektu'));
  elements.projectUpload.value = '';
});
elements.pluginUpload.addEventListener('change', () => {
  const [file] = elements.pluginUpload.files;
  if (file) uploadPlugin(file).catch((error) => reportError(error, 'Import pluginu'));
  elements.pluginUpload.value = '';
});
elements.accountButton.addEventListener('click', async () => {
  if (!state.session.authenticated) return showAuth('login');
  if (!await actionDialog({ title: 'Odhlásit se?', description: 'Přepnete do prostoru pro hosta. Vaše projekty zůstanou uložené.', submit: 'Odhlásit', onSubmit: async () => { if (state.dirty) await saveCurrent(); return true; } })) return;
  await api('api/auth/logout', { method: 'POST', body: '{}' });
  state.project = null;
  await loadSession();
  await loadProjects();
});
elements.authForm.addEventListener('submit', submitAuth);
elements.authSwitch.addEventListener('click', () => showAuth(state.authMode === 'login' ? 'register' : 'login'));
$('#auth-close').addEventListener('click', () => elements.authDialog.close());
$('#settings-button').addEventListener('click', async () => {
  applyAppearance(); showError('#settings-error', null); elements.settingsDialog.showModal();
  try { $('#projects-directory').value = (await getFolderSettings()).projectsDirectory; }
  catch (error) { showError('#settings-error', error); }
});
$('#settings-close').addEventListener('click', () => elements.settingsDialog.close());
elements.settingsForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.submitter; button.disabled = true;
  try {
    const directory = $('#projects-directory').value;
    if (directory !== folderSettings?.projectsDirectory) folderSettings = await api('api/settings', { method: 'PUT', body: JSON.stringify({ projectsDirectory: directory }) });
    saveAppearanceFromForm(); elements.settingsDialog.close(); toast('Nastavení bylo uloženo.');
  } catch (error) { showError('#settings-error', error); }
  finally { button.disabled = false; }
});
$('#font-size-setting').addEventListener('input', (event) => { $('#font-size-output').textContent = `${event.target.value} px`; });
$('#console-height-setting').addEventListener('input', (event) => { $('#console-height-output').textContent = `${event.target.value} px`; });
$('#reset-appearance').addEventListener('click', () => {
  state.appearance = { ...DEFAULT_APPEARANCE };
  localStorage.setItem('oleafAppearance', JSON.stringify(state.appearance));
  applyAppearance();
});
$('#toggle-console').addEventListener('click', toggleConsole);
$('#clear-console').addEventListener('click', () => { state.consoleBuffer = ''; elements.debugConsole.textContent = ''; debug('Konzole byla vyčištěna.'); });
$('#copy-console').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(state.consoleBuffer); toast('Konzole byla zkopírována.'); }
  catch (error) { reportError(error, 'Kopírování konzole'); }
});

window.addEventListener('beforeunload', (event) => {
  if (!state.dirty) return;
  event.preventDefault();
  event.returnValue = '';
});
window.addEventListener('unload', releasePdf);

(async () => {
  try {
    loadAppearance();
    state.consoleBuffer = '';
    debug(`O-Leaf ${document.title} spuštěn; URL=${window.location.pathname}`);
    editor.setOption('readOnly', true);
    await loadSession();
    await Promise.all([loadProjects(), loadPlugins()]);
    setConsoleStatus('success', 'Připraveno');
  } catch (error) { reportError(error, 'Inicializace O-Leafu'); }
})();
