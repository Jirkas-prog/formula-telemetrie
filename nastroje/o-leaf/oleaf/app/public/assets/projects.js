/* global OLeafUI, state, api, $, loadProjects, openFile, toast, reportError, elements, saveCurrent */
'use strict';

let folderSettings = null;
let folderView = null;
let folderMode = 'open';
let folderPicked = null;
let folderRequest = 0;

function showError(selector, error) {
  const node = $(selector);
  node.textContent = error ? error.message || String(error) : '';
  node.hidden = !error;
}

function actionDialog({ title, description = '', label = '', value = '', choices = null, submit = 'Potvrdit', onSubmit }) {
  const dialog = $('#action-dialog');
  $('#action-title').textContent = title;
  $('#action-description').textContent = description;
  $('#action-label').textContent = label;
  $('#action-field').hidden = !label;
  $('#action-input').required = Boolean(label);
  $('#action-input').value = value;
  $('#action-input').hidden = Boolean(choices);
  $('#action-input').required = Boolean(label) && !choices;
  $('#action-choice').hidden = !choices;
  $('#action-choice').replaceChildren(...(choices || []).map((choice) => new Option(choice.label, choice.value)));
  $('#action-submit').textContent = submit;
  showError('#action-error', null);
  return new Promise((resolve) => {
    let result = null;
    let busy = false;
    const cancel = (event) => { if (busy) event.preventDefault(); };
    dialog.addEventListener('cancel', cancel);
    dialog.addEventListener('close', () => { dialog.removeEventListener('cancel', cancel); resolve(result); }, { once: true });
    $('#action-form').onsubmit = async (event) => {
      event.preventDefault();
      if (busy) return;
      busy = true;
      $('#action-submit').disabled = true;
      try {
        result = await onSubmit(choices ? $('#action-choice').value : $('#action-input').value);
        dialog.close();
      } catch (error) { showError('#action-error', error); }
      finally { busy = false; $('#action-submit').disabled = false; }
    };
    dialog.showModal();
    if (choices) $('#action-choice').focus();
    else if (label) { $('#action-input').focus(); $('#action-input').select(); }
  });
}

async function getFolderSettings() {
  folderSettings = await api('api/settings');
  return folderSettings;
}

function renderRecentProjects() {
  const list = $('#recent-projects');
  list.replaceChildren();
  const query = $('#project-search').value.toLocaleLowerCase('cs');
  const projects = state.projects.filter((p) => `${p.name} ${p.externalPath || ''}`.toLocaleLowerCase('cs').includes(query));
  for (const project of projects) {
    const button = document.createElement('button');
    button.className = 'project-card';
    const copy = document.createElement('span');
    const title = document.createElement('strong');
    title.textContent = project.name;
    const location = document.createElement('small');
    location.textContent = project.externalPath || 'Soukromý prostor addonu';
    const date = document.createElement('time');
    date.textContent = new Date(project.updatedAt).toLocaleDateString('cs');
    copy.append(title, location);
    button.append(OLeafUI.icon('folder'), copy, date, OLeafUI.icon('right'));
    button.onclick = async () => {
      button.disabled = true;
      try { await activateProject(project.id); $('#projects-dialog').close(); }
      catch (error) { reportError(error, 'Otevření projektu'); }
      finally { button.disabled = false; }
    };
    list.append(button);
  }
  if (!projects.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-message';
    empty.textContent = state.projects.length ? 'Žádný projekt neodpovídá hledání.' : 'Ještě tu není žádný projekt. Otevřete složku v Home Assistantu nebo vytvořte první dokument.';
    list.append(empty);
  }
}

async function showProjects() {
  $('#project-search').value = '';
  renderRecentProjects();
  $('#projects-dialog').showModal();
  try { state.projects = await api('api/projects'); renderRecentProjects(); }
  catch (error) { reportError(error, 'Načtení projektů'); }
}

async function activateProject(id) {
  await loadProjects(id);
  const files = [];
  const visit = (nodes) => nodes.forEach((node) => node.type === 'directory' ? visit(node.children || []) : files.push(node.path));
  visit(state.projectTree);
  const entry = state.project.entry || (files.includes('main.tex') ? 'main.tex' : files.find((file) => /\.tex$/i.test(file)));
  if (entry && files.includes(entry)) { elements.entryFile.value = entry; await openFile(entry); }
  else if (files.length) await openFile(files[0]);
}

function renderFolderList() {
  const list = $('#folder-list');
  list.replaceChildren();
  if (!folderView) return;
  const query = $('#folder-search').value.toLocaleLowerCase('cs');
  const directories = folderView.directories.filter((item) => item.name.toLocaleLowerCase('cs').includes(query));
  for (const item of directories) {
    const button = document.createElement('button');
    button.className = 'folder-row';
    const name = document.createElement('span');
    name.textContent = item.name;
    button.append(OLeafUI.icon('folder'), name, OLeafUI.icon('right'));
    button.onclick = () => browseFolder(item.path);
    list.append(button);
  }
  if (!directories.length) {
    const message = document.createElement('p');
    message.className = 'empty-message';
    message.textContent = query ? 'Žádná složka neodpovídá hledání.' : 'Žádné další podsložky. Můžete vybrat tuto složku.';
    list.append(message);
  }
}

async function browseFolder(path) {
  const request = ++folderRequest;
  folderView = null;
  $('#folder-path').value = path;
  $('#folder-list').textContent = 'Načítám složky…';
  $('#folder-detail').textContent = '';
  $('#folder-breadcrumbs').replaceChildren();
  $('#folder-select').disabled = true;
  $('#folder-up').disabled = true;
  $('#folder-create').disabled = true;
  showError('#folder-error', null);
  try {
    const view = await api(`api/folders?path=${encodeURIComponent(path)}`);
    if (request !== folderRequest) return;
    folderView = view;
    $('#folder-path').value = view.path;
    $('#folder-up').disabled = !view.parent;
    $('#folder-create').disabled = false;
    $('#folder-select').disabled = folderMode === 'open' && view.roots.includes(view.path);
    $('#folder-search').value = '';
    $('#folder-detail').textContent = folderMode === 'open'
      ? `${view.texFiles.length ? `TeX soubory: ${view.texFiles.join(', ')}. ` : ''}Změny se budou ukládat přímo do této složky.`
      : 'Vyberte tuto složku nebo přejděte do některé podsložky.';
    const parts = view.path.replaceAll('\\', '/').split('/').filter(Boolean);
    parts.forEach((part, index) => {
      const crumb = document.createElement('button');
      crumb.className = 'breadcrumb';
      crumb.textContent = part;
      const dest = (view.path.startsWith('/') ? '/' : '') + parts.slice(0, index + 1).join('/');
      crumb.onclick = () => browseFolder(dest);
      crumb.disabled = index === parts.length - 1 || !view.roots.some((root) => dest.replaceAll('\\', '/').startsWith(root.replaceAll('\\', '/')));
      $('#folder-breadcrumbs').append(crumb);
    });
    renderFolderList();
  } catch (error) {
    if (request !== folderRequest) return;
    $('#folder-list').replaceChildren();
    showError('#folder-error', `Složku nelze otevřít: ${error.message} Vyberte připojené úložiště níže nebo upravte cestu.`);
  }
}

async function showFolderBrowser(mode = 'open', initialPath = '', onPick = null) {
  folderMode = mode;
  folderPicked = onPick;
  $('#folder-title').textContent = mode === 'open' ? 'Otevřít složku jako projekt' : 'Vybrat složku';
  $('#folder-select').textContent = mode === 'open' ? 'Otevřít tuto složku' : 'Vybrat tuto složku';
  $('#folder-roots').replaceChildren();
  $('#folder-list').textContent = 'Načítám úložiště…';
  $('#folder-select').disabled = true;
  $('#folder-dialog').showModal();
  try {
    const settings = await getFolderSettings();
    const choices = [{ name: 'Výchozí složka', path: settings.projectsDirectory }, ...settings.roots.map((path) => ({ name: '/' + path.replaceAll('\\', '/').split('/').pop(), path }))];
    for (const choice of choices) {
      const button = document.createElement('button');
      button.className = 'button';
      button.textContent = choice.name;
      button.onclick = () => browseFolder(choice.path);
      $('#folder-roots').append(button);
    }
    await browseFolder(initialPath || settings.projectsDirectory);
  } catch (error) { showError('#folder-error', error); }
}

async function createNewProject() {
  $('#projects-dialog').close();
  $('#new-project-form').reset();
  $('#new-project-parent').disabled = false;
  $('#new-project-browse').disabled = false;
  showError('#new-project-error', null);
  $('#new-project-dialog').showModal();
  try {
    const settings = await getFolderSettings();
    $('#new-project-parent').value = settings.projectsDirectory;
    updateDestination();
    $('#new-project-name').focus();
  } catch (error) { showError('#new-project-error', error); }
}

function updateDestination() {
  const privateProject = $('#new-project-private').checked;
  $('#new-project-parent').disabled = privateProject;
  $('#new-project-browse').disabled = privateProject;
  $('#new-project-destination').textContent = privateProject ? 'Projekt bude uložen v soukromém prostoru aktuálního účtu.'
    : `Vznikne složka: ${$('#new-project-parent').value.replace(/[\\/]$/, '')}/${$('#new-project-name').value || 'název projektu'}`;
}

function initProjectUX() {
  document.querySelectorAll('[data-close]').forEach((button) => button.addEventListener('click', () => {
    const dialog = document.getElementById(button.dataset.close);
    if (!dialog.querySelector('button[type="submit"]:disabled')) dialog.close();
  }));
  $('#open-projects').onclick = showProjects;
  $('#welcome-open').onclick = showProjects;
  $('#welcome-new').onclick = createNewProject;
  $('#library-new').onclick = createNewProject;
  $('#library-import').onclick = () => { $('#projects-dialog').close(); elements.projectUpload.click(); };
  $('#project-search').oninput = renderRecentProjects;
  $('#browse-ha').onclick = () => { $('#projects-dialog').close(); showFolderBrowser(); };
  $('#folder-search').oninput = renderFolderList;
  $('#folder-up').onclick = () => folderView?.parent && browseFolder(folderView.parent);
  $('#folder-path-form').onsubmit = (event) => { event.preventDefault(); browseFolder($('#folder-path').value); };
  $('#folder-create').onclick = () => {
    if (!folderView) return;
    const parent = folderView.path;
    actionDialog({ title: 'Nová složka', description: parent, label: 'Název složky', submit: 'Vytvořit složku', onSubmit: async (name) => {
      const result = await api('api/folders', { method: 'POST', body: JSON.stringify({ parentPath: parent, name }) });
      await browseFolder(result.path);
      return true;
    } });
  };
  $('#folder-select').onclick = async () => {
    if (!folderView) return;
    const button = $('#folder-select');
    button.disabled = true;
    try {
      if (folderMode === 'open') {
        if (state.dirty) await saveCurrent();
        const project = await api('api/projects/open-folder', { method: 'POST', body: JSON.stringify({ path: folderView.path }) });
        await activateProject(project.id);
        toast('Projekt je otevřen. Změny se ukládají do původní složky.');
      } else if (folderPicked) await folderPicked(folderView.path);
      $('#folder-dialog').close();
    } catch (error) { showError('#folder-error', error); }
    finally { button.disabled = false; }
  };
  $('#new-project-browse').onclick = () => showFolderBrowser('select', $('#new-project-parent').value, (path) => { $('#new-project-parent').value = path; updateDestination(); });
  $('#choose-default-folder').onclick = () => showFolderBrowser('select', $('#projects-directory').value, (path) => { $('#projects-directory').value = path; });
  for (const id of ['#new-project-name', '#new-project-parent', '#new-project-private']) $(id).addEventListener('input', updateDestination);
  $('#new-project-form').onsubmit = async (event) => {
    event.preventDefault();
    const button = event.submitter;
    if (button.disabled) return;
    button.disabled = true;
    showError('#new-project-error', null);
    try {
      if (state.dirty) await saveCurrent();
      const project = await api('api/projects', { method: 'POST', body: JSON.stringify({ name: $('#new-project-name').value, parentPath: $('#new-project-private').checked ? null : $('#new-project-parent').value }) });
      await activateProject(project.id);
      $('#new-project-dialog').close();
      toast('Nový projekt je připraven.');
    } catch (error) { showError('#new-project-error', error); }
    finally { button.disabled = false; }
  };
  $('#file-search').oninput = renderFilteredTree;
  elements.entryFile.addEventListener('change', async () => {
    if (!state.project) return;
    try {
      state.project = await api(`api/projects/${state.project.id}/settings`, { method: 'PUT', body: JSON.stringify({ entry: elements.entryFile.value }) });
      toast('Hlavní soubor byl uložen.');
    } catch (error) { reportError(error, 'Hlavní soubor'); }
  });
}

function renderFilteredTree() {
  const query = $('#file-search').value.toLocaleLowerCase('cs');
  const filter = (nodes) => nodes.flatMap((node) => {
    if (!query || node.path.toLocaleLowerCase('cs').includes(query)) return [node];
    if (node.type !== 'directory') return [];
    const children = filter(node.children || []);
    return children.length ? [{ ...node, children }] : [];
  });
  const nodes = filter(state.projectTree);
  elements.fileTree.replaceChildren(renderTree(nodes, true));
  if (query) elements.fileTree.querySelectorAll('.collapsed').forEach((node) => node.classList.remove('collapsed'));
  if (!nodes.length) elements.fileTree.textContent = query ? 'Žádný odpovídající soubor.' : 'Projekt zatím neobsahuje soubory.';
  syncActiveFileRows();
}
