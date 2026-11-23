/* global CodeMirror */
'use strict';

// Preferences contain layout only; documents and accounts are never stored here.
(function (root) {
  const clampRatio = (value) => Math.max(.12, Math.min(.88, Number(value) || .5));
  const fitRatio = (value, width, dividerWidth) => {
    const minimum = Math.min(.5, 128 / Math.max(1, width - dividerWidth));
    return Math.max(minimum, Math.min(1 - minimum, clampRatio(value)));
  };
  function resolveLayout(saved, compact) {
    return {
      ratio: clampRatio(saved?.ratio),
      mode: ['split', 'editor', 'pdf'].includes(saved?.mode) ? saved.mode : compact ? 'editor' : 'split',
      sidebar: typeof saved?.sidebar === 'boolean' ? saved.sidebar : !compact,
    };
  }
  function dividerAction(mode, side) {
    if (mode === 'pdf') return side === 'left' ? 'split' : 'editor';
    if (mode === 'editor') return side === 'left' ? 'pdf' : 'split';
    return side === 'left' ? 'pdf' : 'editor';
  }
  const paths = {
    folder: 'M3 6h7l2 3h9v11H3z',
    folderOpen: 'M3 6h7l2 3h8v3 M3 6v14h16l3-8H6z',
    folderPlus: 'M3 6h7l2 3h9v11H3z M12 11v6 M9 14h6',
    settings: 'M4 7h16 M4 17h16 M9 4v6 M15 14v6',
    image: 'M3 3h18v18H3z M3 17l6-7 5 5 3-3 4 5 M16 7h1',
    bib: 'M3 4h7l2 2 2-2h7v16h-7l-2 1-2-1H3z M12 6v15',
    file: 'M14 3H5v18h14V8z M14 3v5h5',
    new: 'M14 3H5v18h14V8z M14 3v5h5 M8 14h8 M12 10v8',
    import: 'M4 14v6h16v-6 M12 3v12 M7 10l5 5 5-5',
    export: 'M4 14v6h16v-6 M12 15V3 M7 8l5-5 5 5',
    save: 'M5 3h12l4 4v14H3V3z M7 3v6h9V3 M7 21v-8h10v8',
    compile: 'M8 4l12 8-12 8z',
    pdf: 'M14 3H5v18h14V8z M14 3v5h5 M8 12h8 M8 16h6',
    editor: 'M8 6l-6 6 6 6 M16 6l6 6-6 6 M14 3l-4 18',
    left: 'M15 5l-7 7 7 7',
    right: 'M9 5l7 7-7 7',
    doubleLeft: 'M12 5l-7 7 7 7 M19 5l-7 7 7 7',
    doubleRight: 'M5 5l7 7-7 7 M12 5l7 7-7 7',
    copy: 'M8 8h13v13H8z M16 8V3H3v13h5',
    clear: 'M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7',
  };
  function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'action-icon');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const path = document.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('d', paths[name] || paths.pdf);
    svg.append(path);
    return svg;
  }
  function setActionLabel(button, label, name = button.dataset.icon) {
    const text = document.createElement('span');
    text.className = 'action-label';
    text.textContent = label;
    button.replaceChildren(icon(name), text);
    button.dataset.icon = name;
    button.setAttribute('aria-label', label);
    button.title = label;
  }
  const api = { clampRatio, fitRatio, resolveLayout, dividerAction, setActionLabel, icon };
  if (typeof module !== 'undefined') module.exports = api;
  if (!root.document) return;
  root.OLeafUI = api;

  api.init = ({ editor }) => {
    const $ = (id) => document.getElementById(id);
    const compact = matchMedia('(max-width: 700px)');
    const workspace = document.querySelector('.workspace');
    const workbench = $('workbench');
    const sidebar = $('project-sidebar');
    const sidebarToggle = $('sidebar-toggle');
    const backdrop = $('sidebar-backdrop');
    const resize = $('pane-resize');
    const left = $('pane-left');
    const right = $('pane-right');
    const storageKey = () => `oleafLayout:${compact.matches ? 'narrow' : 'wide'}`;
    const read = () => {
      try { return resolveLayout(JSON.parse(localStorage.getItem(storageKey())), compact.matches); }
      catch { return resolveLayout(null, compact.matches); }
    };
    let layout = read();
    let drag = null;
    let frame = 0;
    const persist = () => {
      try { localStorage.setItem(storageKey(), JSON.stringify(layout)); } catch { /* Private browsing can disable storage. */ }
    };
    document.querySelectorAll('[data-icon]').forEach((button) => setActionLabel(button, button.textContent.trim()));
    setActionLabel($('copy-console'), 'Kopírovat celý log', 'copy');
    setActionLabel($('clear-console'), 'Vyčistit konzoli', 'clear');

    function arrow(button, name, label) {
      button.replaceChildren(icon(name));
      button.title = label;
      button.setAttribute('aria-label', label);
    }
    function refreshEditor() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { if (!$('editor-pane').hidden) editor.refresh(); });
    }
    function applyTracks() {
      const visibleRatio = fitRatio(layout.ratio, workbench.clientWidth, $('pane-divider').getBoundingClientRect().width);
      workbench.style.setProperty('--editor-share', `${visibleRatio}fr`);
      workbench.style.setProperty('--pdf-share', `${1 - visibleRatio}fr`);
      const value = layout.mode === 'pdf' ? 0 : layout.mode === 'editor' ? 100 : Math.round(visibleRatio * 100);
      resize.setAttribute('aria-valuenow', String(value));
      resize.setAttribute('aria-valuetext', layout.mode === 'split' ? `Editor ${value} %, PDF ${100 - value} %` : layout.mode === 'pdf' ? 'Pouze PDF' : 'Pouze editor');
    }
    function render() {
      workspace.classList.toggle('sidebar-collapsed', !layout.sidebar);
      sidebar.hidden = !layout.sidebar;
      sidebarToggle.setAttribute('aria-expanded', String(layout.sidebar));
      arrow(sidebarToggle, layout.sidebar ? 'left' : 'right', layout.sidebar ? 'Skrýt navigaci' : 'Otevřít navigaci');
      backdrop.hidden = !compact.matches || !layout.sidebar;
      workbench.inert = !backdrop.hidden;
      $('console-pane').inert = !backdrop.hidden;
      workbench.dataset.mode = layout.mode;
      $('editor-pane').hidden = layout.mode === 'pdf';
      $('preview-pane').hidden = layout.mode === 'editor';
      applyTracks();
      if (layout.mode === 'pdf') {
        arrow(left, 'right', 'Vrátit rozdělení editoru a PDF');
        arrow(right, 'doubleRight', 'Editor přes celou pracovní plochu');
      } else if (layout.mode === 'editor') {
        arrow(left, 'doubleLeft', 'PDF přes celou pracovní plochu');
        arrow(right, 'left', 'Vrátit rozdělení editoru a PDF');
      } else {
        arrow(left, 'left', 'PDF přes celou pracovní plochu');
        arrow(right, 'right', 'Editor přes celou pracovní plochu');
      }
      setActionLabel($('pane-toggle'), layout.mode === 'pdf' ? 'Editor' : 'PDF', layout.mode === 'pdf' ? 'editor' : 'pdf');
      $('pane-toggle').setAttribute('aria-pressed', String(layout.mode === 'pdf'));
      refreshEditor();
    }
    api.setMode = (mode) => {
      if (!['split', 'editor', 'pdf'].includes(mode)) return;
      const hiddenPane = $(mode === 'pdf' ? 'editor-pane' : 'preview-pane');
      if (mode !== 'split' && hiddenPane.contains(document.activeElement)) resize.focus();
      layout.mode = mode;
      render();
      persist();
    };
    api.showMobilePreview = (show) => { if (compact.matches) api.setMode(show ? 'pdf' : 'editor'); };
    api.togglePane = () => api.setMode(layout.mode === 'pdf' ? 'editor' : 'pdf');
    const setSidebar = (open) => {
      if (!open && sidebar.contains(document.activeElement)) sidebarToggle.focus();
      layout.sidebar = open;
      render();
      persist();
    };
    sidebarToggle.addEventListener('click', () => setSidebar(!layout.sidebar));
    backdrop.addEventListener('click', () => setSidebar(false));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && compact.matches && layout.sidebar && !document.querySelector('dialog[open]')) setSidebar(false);
    });
    left.addEventListener('click', () => api.setMode(dividerAction(layout.mode, 'left')));
    right.addEventListener('click', () => api.setMode(dividerAction(layout.mode, 'right')));
    resize.addEventListener('keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Enter'].includes(event.key)) return;
      event.preventDefault();
      if (event.key === 'Home') return api.setMode('pdf');
      if (event.key === 'End') return api.setMode('editor');
      if (event.key === 'Enter') return api.setMode('split');
      const current = layout.mode === 'pdf' ? 0 : layout.mode === 'editor' ? 1 : Number(resize.getAttribute('aria-valuenow')) / 100;
      layout.ratio = clampRatio(current + (event.key === 'ArrowLeft' ? -1 : 1) * (event.shiftKey ? .1 : .02));
      api.setMode('split');
    });
    resize.addEventListener('pointerdown', (event) => {
      if (event.button !== 0 || drag) return;
      const rect = workbench.getBoundingClientRect();
      const handle = resize.getBoundingClientRect();
      drag = { id: event.pointerId, x: event.clientX, offset: event.clientX - handle.left, left: rect.left, width: rect.width - handle.width };
      resize.setPointerCapture(event.pointerId);
      resize.focus({ preventScroll: true });
      document.body.classList.add('resizing-panes');
      event.preventDefault();
    });
    resize.addEventListener('pointermove', (event) => {
      if (!drag || event.pointerId !== drag.id || Math.abs(event.clientX - drag.x) < 2) return;
      layout.ratio = clampRatio((event.clientX - drag.left - drag.offset) / Math.max(1, drag.width));
      layout.mode = 'split';
      render();
    });
    function stopDrag(event) {
      if (!drag || event.pointerId !== drag.id) return;
      drag = null;
      document.body.classList.remove('resizing-panes');
      persist();
    }
    resize.addEventListener('pointerup', stopDrag);
    resize.addEventListener('pointercancel', stopDrag);
    resize.addEventListener('lostpointercapture', stopDrag);
    compact.addEventListener('change', () => { layout = read(); render(); });
    new ResizeObserver(refreshEditor).observe($('editor-pane'));
    new ResizeObserver(applyTracks).observe(workbench);
    const inputType = (event) => {
      // No DOM cursor overlay, including on hybrid touch + mouse devices.
      document.documentElement.dataset.input = event.pointerType === 'touch' ? 'touch' : 'mouse';
    };
    document.addEventListener('pointerdown', inputType, { passive: true });
    document.addEventListener('pointermove', inputType, { passive: true });
    render();
  };
})(typeof window !== 'undefined' ? window : globalThis);
