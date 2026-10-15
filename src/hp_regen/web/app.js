'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { token: null, demo: false, devices: [], selected: null, bridgePlan: null, queuesAvailable: false };
  let toastTimer;

  function text(value) {
    if (value === undefined || value === null || value === '') return 'Nieznane';
    if (value === true) return 'Tak';
    if (value === false) return 'Nie';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return String(value);
  }

  function element(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = text(content);
    return node;
  }

  function message(id, content, type = '') {
    const node = $(id);
    node.textContent = content;
    node.className = `inline-message${type ? ` ${type}` : ''}`;
    node.hidden = !content;
  }

  function toast(content) {
    $('toast').textContent = content;
    $('toast').hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { $('toast').hidden = true; }, 6000);
  }

  async function api(path, body) {
    if (body && !state.token) throw new Error('Brak aktywnej sesji. Odśwież warsztat i spróbuj ponownie.');
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 45000);
    try {
      const options = { method: body ? 'POST' : 'GET', cache: 'no-store', credentials: 'omit', mode: 'same-origin', redirect: 'error', signal: controller.signal, headers: { Accept: 'application/json' } };
      if (body) {
        options.headers['Content-Type'] = 'application/json';
        options.headers['X-Regen-Token'] = state.token;
        options.body = JSON.stringify(body);
      }
      const response = await fetch(path, options);
      let data;
      try { data = await response.json(); }
      catch (_) { throw new Error('Warsztat zwrócił niepoprawną odpowiedź.'); }
      if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : `Operacja nie powiodła się (${response.status}).`);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Przekroczono czas oczekiwania. Operacja nie została potwierdzona.');
      if (error instanceof TypeError) throw new Error('Nie można połączyć się z lokalnym warsztatem. Sprawdź, czy serwer działa.');
      throw error;
    } finally { window.clearTimeout(timer); }
  }

  async function busy(button, label, operation) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = label;
    try { return await operation(); }
    finally { button.textContent = original; button.disabled = false; }
  }

  function requireNetworkPermission() {
    if (!$('network-ack').checked) throw new Error('Zaznacz zgodę na dostęp do własnej sieci w zakładce Urządzenia.');
  }

  function showPage(name, focus = true) {
    if (!['devices', 'diagnostics', 'firmware', 'compatibility'].includes(name)) return;
    document.querySelectorAll('.page').forEach((page) => {
      const active = page.id === `page-${name}`;
      page.hidden = !active;
      page.classList.toggle('active-page', active);
    });
    document.querySelectorAll('[data-page]').forEach((button) => {
      const active = button.dataset.page === name;
      button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    if (focus) {
      $('main-content').focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: 'instant' });
    }
  }

  function addDevice(device) {
    if (!device || typeof device !== 'object' || typeof device.uri !== 'string') return;
    const index = state.devices.findIndex((entry) => entry.uri === device.uri);
    if (index >= 0) state.devices[index] = { ...state.devices[index], ...device };
    else state.devices.push(device);
  }

  function renderDevices() {
    $('device-grid').replaceChildren();
    $('device-count').textContent = String(state.devices.length).padStart(2, '0');
    $('inventory-count').textContent = String(state.devices.length);
    $('nav-count').textContent = String(state.devices.length);
    $('device-empty').hidden = state.devices.length > 0;
    state.devices.forEach((device) => {
      const selected = state.selected && state.selected.uri === device.uri;
      const card = element('article', `device-card${selected ? ' selected' : ''}`);
      const top = element('div', 'device-top');
      const icon = element('div', 'device-icon', '▤');
      icon.setAttribute('aria-hidden', 'true');
      top.append(icon, element('span', 'device-source', device.source || 'IPP'));
      const button = element('button', 'button secondary', selected ? 'Wybrane urządzenie ↗' : 'Otwórz urządzenie ↗');
      button.type = 'button';
      button.setAttribute('aria-label', `Otwórz urządzenie: ${text(device.name || device.model || 'Drukarka bez nazwy')}`);
      button.addEventListener('click', () => selectDevice(device));
      card.append(top, element('h3', '', device.name || device.model || 'Drukarka bez nazwy'), element('p', '', device.model || 'Model jeszcze nieodczytany'), element('p', 'device-uri', device.uri), button);
      $('device-grid').append(card);
    });
  }

  function selectDevice(device) {
    const sameDevice = state.selected && state.selected.uri === device.uri;
    state.selected = device;
    $('inspection-empty').hidden = true;
    $('inspection-workspace').hidden = false;
    $('selected-name').textContent = text(device.name || device.model || 'Drukarka bez nazwy');
    $('selected-uri').textContent = device.uri;
    if (!sameDevice) {
      $('inspection-result').hidden = true;
      message('inspection-message', 'Urządzenie wybrane. Kliknij „Odczytaj stan”, aby wysłać zapytanie IPP.');
      invalidateBridgePlan();
    }
    renderDevices();
    showPage('diagnostics');
  }

  function displayFields(target, entries) {
    const list = element('dl', 'result-fields');
    entries.forEach(([label, value]) => list.append(element('dt', '', label), element('dd', '', value)));
    target.replaceChildren(list);
  }

  function renderInspection(device) {
    const states = { 3: 'Bezczynna', 4: 'Drukuje', 5: 'Zatrzymana', idle: 'Bezczynna', processing: 'Przetwarza', stopped: 'Zatrzymana' };
    $('inspection-summary').replaceChildren();
    const fields = [['Model', device.model], ['Stan IPP', states[device.state] || device.state], ['Firmware', device.firmware === 'unknown' ? 'Nieudostępnione' : device.firmware]];
    fields.forEach(([label, value]) => {
      const card = element('div', 'diagnostic-card');
      card.append(element('label', '', label), element('strong', '', value));
      $('inspection-summary').append(card);
    });
    $('inspection-findings').replaceChildren();
    const findings = Array.isArray(device.findings) ? [...device.findings] : [];
    const details = findings.length ? findings : ['Brak dodatkowych wskazówek w odpowiedzi. Nie oznacza to potwierdzenia sprawności urządzenia.'];
    if (device.reasons) details.push({ 'Powody stanu IPP': device.reasons });
    if (device.capabilities) details.push({ 'Zgłoszone możliwości': device.capabilities });
    details.forEach((finding) => {
      const row = element('div', 'finding');
      const content = typeof finding === 'object' && finding !== null ? (finding.detail || finding.message || finding.description || finding) : finding;
      const marker = element('span', '', '↗');
      marker.setAttribute('aria-hidden', 'true');
      row.append(marker, element('p', '', content));
      $('inspection-findings').append(row);
    });
    $('inspection-raw').textContent = JSON.stringify(device.attributes || {}, null, 2);
    $('inspection-result').hidden = false;
  }

  async function inspect(uri, button) {
    requireNetworkPermission();
    message('inspection-message', 'Trwa odczyt atrybutów IPP. Bez zmiany ustawień drukarki.');
    await busy(button, 'Odczytywanie…', async () => {
      const response = await api('/api/inspect', { uri, acknowledged: true });
      if (!response.device || typeof response.device !== 'object') throw new Error('Brak danych urządzenia w odpowiedzi.');
      const canonicalUri = response.device.uri;
      if (typeof canonicalUri !== 'string' || !canonicalUri) throw new Error('Brak znormalizowanego adresu urządzenia w odpowiedzi.');
      const existingDevice = state.devices.find((entry) => entry.uri === uri);
      const device = { ...existingDevice, ...response.device };
      const selected = state.selected && state.selected.uri === uri;
      if (canonicalUri !== uri) state.devices = state.devices.filter((entry) => entry.uri !== uri);
      addDevice(device);
      if (selected) {
        state.selected = device;
        $('selected-name').textContent = text(device.name || device.model || 'Drukarka bez nazwy');
        $('selected-uri').textContent = canonicalUri;
        if (canonicalUri !== uri) invalidateBridgePlan();
        renderInspection(device);
        message('inspection-message', state.demo ? 'Odczyt DEMO: pokazano przykładową odpowiedź. Nie połączono się z drukarką.' : 'Odczyt zakończony. Nie zmieniono ustawień ani firmware urządzenia.');
      }
      renderDevices();
    });
  }

  document.querySelectorAll('[data-page]').forEach((button) => button.addEventListener('click', () => showPage(button.dataset.page)));
  document.querySelectorAll('[data-go]').forEach((button) => button.addEventListener('click', () => showPage(button.dataset.go)));

  $('discovery-method').addEventListener('change', () => {
    const subnet = $('discovery-method').value === 'subnet';
    $('subnet-field').hidden = !subnet;
    $('subnet-cidr').required = subnet;
  });

  $('discovery-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    message('discovery-message', '');
    try {
      requireNetworkPermission();
      const body = { method: $('discovery-method').value, acknowledged: true };
      if (body.method === 'subnet') body.cidr = $('subnet-cidr').value.trim();
      message('discovery-message', state.demo ? 'Tryb DEMO: ładowanie przykładowych urządzeń…' : 'Trwa ograniczone wykrywanie urządzeń. To może potrwać kilka sekund.');
      await busy($('discover-button'), 'Wykrywanie…', async () => {
        const response = await api('/api/discover', body);
        if (!Array.isArray(response.devices)) throw new Error('Brak listy urządzeń w odpowiedzi.');
        response.devices.forEach(addDevice);
        renderDevices();
        const warnings = Array.isArray(response.warnings) ? response.warnings.map(text) : [];
        const prefix = state.demo ? 'DEMO: przykładowe wyniki. Nie wykonano skanowania sieci.' : `Wykrywanie zakończone. Wyniki: ${response.devices.length}.`;
        message('discovery-message', [prefix, ...warnings].join('\n'), warnings.length ? 'warning' : '');
      });
    } catch (error) { message('discovery-message', error.message, 'error'); }
  });

  $('manual-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      requireNetworkPermission();
      const uri = $('printer-uri').value.trim();
      const device = { uri, name: 'Drukarka z podanego adresu', source: 'adres ręczny' };
      selectDevice(device);
      await inspect(uri, $('manual-button'));
    } catch (error) {
      message('discovery-message', error.message, 'error');
      message('inspection-message', error.message, 'error');
    }
  });

  $('inspect-button').addEventListener('click', async () => {
    if (!state.selected) return;
    try { await inspect(state.selected.uri, $('inspect-button')); }
    catch (error) { message('inspection-message', error.message, 'error'); }
  });

  $('report-button').addEventListener('click', async () => {
    try {
      await busy($('report-button'), 'Przygotowywanie…', async () => {
        const response = await api('/api/report');
        const blob = new Blob([JSON.stringify(response.report ?? response, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'hp-regen-raport.json';
        document.body.append(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 2000);
        toast(state.demo ? 'Pobrano raport DEMO z przykładowymi danymi.' : 'Pobrano raport JSON. Przed udostępnieniem sprawdź, czy nie zawiera danych Twojej sieci.');
      });
    } catch (error) { toast(error.message); }
  });

  async function fileBase64(file) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 32768) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
    }
    return btoa(binary);
  }

  const fieldLabels = {
    integrity_matches: 'Suma SHA-256 zgodna', model_matches: 'Dokładny model zgodny', size_matches: 'Rozmiar zgodny',
    ready_to_flash: 'Gotowość do flashowania', authenticity: 'Autentyczność', write_adapter: 'Adapter zapisu',
    computed_sha256: 'Obliczona suma SHA-256', checks: 'Przeprowadzone kontrole', warnings: 'Uwagi',
    status: 'Status', capabilities: 'Możliwości', firmware: 'Firmware', details: 'Szczegóły', source_url: 'Źródło'
  };
  const knownValues = { unverified: 'Niezweryfikowana', unavailable: 'Niedostępny', unsupported: 'Brak obsługi', planned: 'Planowane', experimental: 'Eksperymentalne' };
  function translatedValue(value) { return typeof value === 'string' && knownValues[value] ? knownValues[value] : value; }

  $('firmware-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    message('firmware-message', '');
    $('preflight-result-panel').hidden = true;
    try {
      const file = $('firmware-file').files[0];
      if (!file) throw new Error('Wybierz plik obrazu firmware.');
      if (file.size === 0) throw new Error('Plik firmware jest pusty.');
      if (file.size > 4 * 1024 * 1024) throw new Error('Plik przekracza limit 4 MiB tej wersji warsztatu.');
      let manifest;
      try { manifest = JSON.parse($('firmware-manifest').value); }
      catch (_) { throw new Error('Manifest nie jest poprawnym JSON-em. Sprawdź nawiasy, przecinki i cudzysłowy.'); }
      if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) throw new Error('Manifest musi być obiektem JSON.');
      const model = $('firmware-model').value.trim();
      if (!model) throw new Error('Podaj dokładny model urządzenia.');
      await busy($('preflight-button'), 'Sprawdzanie pakietu…', async () => {
        const response = await api('/api/firmware/preflight', { manifest, data_base64: await fileBase64(file), model });
        if (!response.preflight || typeof response.preflight !== 'object') throw new Error('Brak wyniku preflight w odpowiedzi.');
        const preflight = response.preflight;
        displayFields($('preflight-result'), Object.entries(preflight).map(([key, value]) => [fieldLabels[key] || key, translatedValue(value)]));
        $('preflight-result-panel').hidden = false;
        message('firmware-message', 'Sprawdzono plik lokalnie. Autentyczność pozostaje niezweryfikowana. Adapter zapisu jest niedostępny.');
      });
    } catch (error) { message('firmware-message', error.message, 'error'); }
  });

  function renderCompatibility(entries) {
    $('compatibility-grid').replaceChildren();
    $('compatibility-empty').hidden = entries.length > 0;
    entries.forEach((entry) => {
      if (!entry || typeof entry !== 'object') return;
      const card = element('article', 'panel compatibility-card');
      const title = element('h2', '', entry.name || entry.model || entry.id || 'Wpis zgodności');
      const fields = element('div');
      displayFields(fields, Object.entries(entry).filter(([key]) => !['name', 'id', 'model'].includes(key)).map(([key, value]) => [fieldLabels[key] || key, translatedValue(value)]));
      card.append(title, fields);
      $('compatibility-grid').append(card);
    });
  }

  function invalidateBridgePlan() {
    state.bridgePlan = null;
    $('bridge-plan').hidden = true;
    $('bridge-ack').checked = false;
    $('bridge-install-button').disabled = true;
    message('bridge-message', '');
  }

  $('queue-name').addEventListener('input', invalidateBridgePlan);
  $('bridge-ack').addEventListener('change', () => {
    $('bridge-install-button').disabled = !($('bridge-ack').checked && state.bridgePlan && state.bridgePlan.supported && !state.demo && state.queuesAvailable);
  });

  async function loadQueues() {
    try {
      const response = await api('/api/queues');
      state.queuesAvailable = response.available === true;
      $('cups-status').textContent = state.queuesAvailable ? 'CUPS: DOSTĘPNY' : 'CUPS: NIEDOSTĘPNY';
      $('queue-list').replaceChildren();
      const queues = Array.isArray(response.queues) ? response.queues : [];
      queues.forEach((queue) => $('queue-list').append(element('li', '', `${text(queue.name)} · ${text(queue.uri)}`)));
      $('existing-queues').hidden = queues.length === 0;
    } catch (_) { $('cups-status').textContent = 'CUPS: NIEZNANY'; }
  }

  $('bridge-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!state.selected) return;
    invalidateBridgePlan();
    try {
      const body = { uri: state.selected.uri, queue_name: $('queue-name').value.trim() };
      await busy($('bridge-plan-button'), 'Przygotowywanie planu…', async () => {
        const response = await api('/api/bridge/plan', body);
        if (!state.selected || state.selected.uri !== body.uri || $('queue-name').value.trim() !== body.queue_name) {
          message('bridge-message', 'Wybór urządzenia lub nazwa kolejki zmieniły się. Przygotuj nowy plan.');
          return;
        }
        state.bridgePlan = { ...body, supported: response.supported === true };
        $('bridge-command').textContent = Array.isArray(response.command) ? response.command.map(text).join(' ') : 'Brak dostępnego polecenia.';
        $('bridge-instructions').replaceChildren();
        if (Array.isArray(response.instructions)) response.instructions.forEach((item) => $('bridge-instructions').append(element('p', '', item)));
        $('bridge-plan').hidden = false;
        message('bridge-message', state.demo ? 'DEMO: podgląd planu. Dodawanie kolejki jest wyłączone w trybie demonstracyjnym.' : (response.supported ? 'Plan gotowy. Dodanie kolejki zmieni konfigurację drukowania na tym komputerze.' : 'Ten system lub adres nie ma obsługi instalacji kolejki.'), 'warning');
      });
    } catch (error) { message('bridge-message', error.message, 'error'); }
  });

  $('bridge-install-button').addEventListener('click', async () => {
    const plan = state.bridgePlan;
    if (!plan || !plan.supported || state.demo || !$('bridge-ack').checked) return;
    try {
      requireNetworkPermission();
      await busy($('bridge-install-button'), 'Dodawanie kolejki…', async () => {
        const response = await api('/api/bridge/install', { uri: plan.uri, queue_name: plan.queue_name, acknowledged: true });
        if (response.installed !== true) throw new Error('Serwer nie potwierdził dodania kolejki.');
        message('bridge-message', `Dodano lokalną kolejkę: ${text(response.queue_name)}. To nie potwierdza udanego wydruku.\n${text(response.output || '')}`);
        $('bridge-ack').checked = false;
        await loadQueues();
      });
    } catch (error) { message('bridge-message', error.message, 'error'); }
    finally { $('bridge-install-button').disabled = !$('bridge-ack').checked; }
  });

  async function boot() {
    renderDevices();
    try {
      const session = await api('/api/session');
      if (typeof session.csrf_token !== 'string' || !session.csrf_token) throw new Error('Brak tokenu lokalnej sesji.');
      state.token = session.csrf_token;
      state.demo = session.demo === true;
      $('demo-banner').hidden = !state.demo;
      $('session-dot').classList.remove('pending');
      $('session-status').textContent = state.demo ? 'Tryb demo · przykładowe dane' : 'Warsztat lokalny · aktywny';
      $('version').textContent = session.version ? `v${String(session.version).replace(/^v/, '')}` : 'v0.1';
      const results = await Promise.allSettled([api('/api/devices'), api('/api/compatibility'), loadQueues()]);
      if (results[0].status === 'fulfilled') {
        const devices = results[0].value.devices;
        if (Array.isArray(devices)) devices.forEach(addDevice);
        renderDevices();
      } else message('discovery-message', results[0].reason.message, 'error');
      if (results[1].status === 'fulfilled') renderCompatibility(Array.isArray(results[1].value.entries) ? results[1].value.entries : []);
      else {
        $('compatibility-empty').hidden = false;
        $('compatibility-empty').textContent = results[1].reason.message;
      }
    } catch (error) {
      $('session-dot').classList.remove('pending');
      $('session-dot').classList.add('error');
      $('session-status').textContent = 'Warsztat niedostępny';
      $('global-error').textContent = error.message;
      $('global-error').hidden = false;
    }
  }

  boot();
})();
