const ENABLE_MWEB = window.CONFIG && window.CONFIG.ENABLE_MWEB;
const shortcut = document.getElementById('shortcut');
const hero           = document.getElementById('hero');
const aiToggleBtn    = document.getElementById('aiToggleBtn');
const submitBtn      = document.getElementById('submitBtn');
const searchProgress = document.getElementById('searchProgress');
const results        = document.getElementById('results');
const input          = document.getElementById('searchInput');
const historyList    = document.getElementById('historyList');
const clearBtn       = document.getElementById('clearHistory');
const sidebar        = document.getElementById('sidebar');
const collapseBtn    = document.getElementById('sidebarCollapse');
const expandBtn      = document.getElementById('sidebarExpand');
const historyBadge   = document.getElementById('historyBadge');
let currentQuery = '';
let searching = false;
let activeAbortCtrl = null;
let activeSearchToken = 0;
let currentData = null;
let sortMode = 'relevance';
let currentPage = 1;
let sourceFilter = 'all';
let dateField = 'mtime';
let dateRange = 'all';
let dateFrom = null;
let dateTo = null;
let dateFilterOpen = false;
let aiModeEnabled = true;
const smartSearchAvailable = window.CONFIG && window.CONFIG.SMART_SEARCH_AVAILABLE;
const PAGE_SIZE = 25;

if (smartSearchAvailable) {
  if (aiToggleBtn) aiToggleBtn.style.display = 'inline-flex';
} else {
  if (aiToggleBtn) aiToggleBtn.style.display = 'none';
  aiModeEnabled = false;
}

const SIDEBAR_STATE_KEY = 'es_sidebar_collapsed';

const HISTORY_KEY = 'es_search_history';
const MAX_HISTORY = 50;

const FILE_ICONS = {
  '.docx': ['docx', 'W'], '.doc': ['docx', 'W'],
  '.xlsx': ['xlsx', 'X'], '.xls': ['xlsx', 'X'], '.csv': ['xlsx', 'C'],
  '.pptx': ['pptx', 'P'], '.ppt': ['pptx', 'P'],
  '.pdf':  ['pdf',  'P'],
  '.txt':  ['txt',  'T'], '.md': ['txt', 'M'], '.log': ['txt', 'L'],
  '.jpg': ['img', '🖼'], '.jpeg': ['img', '🖼'], '.png': ['img', '🖼'],
  '.gif': ['img', '🖼'], '.bmp': ['img', '🖼'], '.svg': ['img', '🖼'],
  '.py': ['code', 'Py'], '.js': ['code', 'JS'], '.ts': ['code', 'TS'],
  '.json': ['code', '{ }'], '.html': ['code', '<>'], '.css': ['code', '#'],
  '.go': ['code', 'Go'], '.java': ['code', 'J'], '.sql': ['code', 'Q'],
};

function iconFor(ext, sourceType) {
  if (sourceType === 'mweb') return ['mweb', '📓'];
  const m = FILE_ICONS[ext];
  return m || ['other', '?'];
}

function setSource(s) {
  sourceFilter = s;
  currentQuery = input.value.trim();
  if (currentQuery) doSearch(currentQuery);
}

function toggleDateFilter() {
  dateFilterOpen = !dateFilterOpen;
  if (!dateFilterOpen && dateRange !== 'all') {
    dateRange = 'all';
    dateFrom = null;
    dateTo = null;
    currentQuery = input.value.trim();
    if (currentQuery) { doSearch(currentQuery); return; }
  }
  renderView();
}

function setDateField(f) {
  dateField = f;
  currentQuery = input.value.trim();
  if (currentQuery) doSearch(currentQuery);
}

function setDateRange(range) {
  dateRange = range;
  const now = Math.floor(Date.now() / 1000);
  const DAY = 86400;
  switch (range) {
    case 'week':   dateFrom = now - 7 * DAY; dateTo = null; break;
    case 'month':  dateFrom = now - 30 * DAY; dateTo = null; break;
    case '3month': dateFrom = now - 90 * DAY; dateTo = null; break;
    case 'year':   dateFrom = now - 365 * DAY; dateTo = null; break;
    case 'custom': return;
    default:       dateFrom = null; dateTo = null;
  }
  currentQuery = input.value.trim();
  if (currentQuery) doSearch(currentQuery);
}

function applyCustomDate() {
  const fromEl = document.getElementById('dateFromInput');
  const toEl = document.getElementById('dateToInput');
  if (fromEl && fromEl.value) {
    dateFrom = new Date(fromEl.value + 'T00:00:00').getTime() / 1000;
  } else {
    dateFrom = null;
  }
  if (toEl && toEl.value) {
    dateTo = new Date(toEl.value + 'T23:59:59').getTime() / 1000;
  } else {
    dateTo = null;
  }
  currentQuery = input.value.trim();
  if (currentQuery) doSearch(currentQuery);
}

function shortenPath(fp) {
  return fp.replace(/^\/Users\/[^/]+\//, '~/');
}

/* ---- 仅回车或搜索按钮触发搜索，输入过程不做任何动作 ---- */

/* ---- Search History ---- */

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY)) || [];
  } catch { return []; }
}

function saveHistory(history) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
}

function addToHistory(query, resultCount) {
  const history = loadHistory();
  const idx = history.findIndex(h => h.query === query);
  if (idx !== -1) history.splice(idx, 1);
  history.unshift({ query, resultCount, timestamp: Date.now() });
  if (history.length > MAX_HISTORY) history.length = MAX_HISTORY;
  saveHistory(history);
  renderHistory();
}

function formatTime(ts) {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function updateSidebarVisibility(historyCount) {
  if (historyCount === 0) {
    sidebar.classList.add('hidden');
    sidebar.classList.remove('collapsed');
    return;
  }
  sidebar.classList.remove('hidden');
  const userCollapsed = localStorage.getItem(SIDEBAR_STATE_KEY) === '1';
  if (userCollapsed) {
    sidebar.classList.add('collapsed');
  } else {
    sidebar.classList.remove('collapsed');
  }
  historyBadge.textContent = historyCount;
}

function renderHistory() {
  const history = loadHistory();
  updateSidebarVisibility(history.length);
  if (!history.length) {
    historyList.innerHTML = '';
    return;
  }
  historyList.innerHTML = history.map(h => `
    <div class="history-item${h.query === currentQuery ? ' active' : ''}"
         data-query="${esc(h.query)}">
      <div class="history-query">${esc(h.query)}</div>
      <div class="history-meta">
        <span class="history-count">📄 ${h.resultCount} 个结果</span>
        <span class="history-time">${formatTime(h.timestamp)}</span>
      </div>
    </div>
  `).join('');
}

historyList.addEventListener('click', e => {
  const item = e.target.closest('.history-item');
  if (!item || searching) return;
  const q = item.dataset.query;
  input.value = q;
  input.focus();
  /* 只填框不搜索，用户按回车后再搜索 */
});

collapseBtn.addEventListener('click', () => {
  localStorage.setItem(SIDEBAR_STATE_KEY, '1');
  sidebar.classList.add('collapsed');
});

expandBtn.addEventListener('click', () => {
  localStorage.removeItem(SIDEBAR_STATE_KEY);
  sidebar.classList.remove('collapsed');
});

clearBtn.addEventListener('click', () => {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
});

/* ---- Sorting ---- */

function getSortedResults(items) {
  const arr = [...items];
  if (sortMode === 'mtime_desc') {
    arr.sort((a, b) => (b.mtime || 0) - (a.mtime || 0));
  } else if (sortMode === 'mtime_asc') {
    arr.sort((a, b) => (a.mtime || 0) - (b.mtime || 0));
  }
  return arr;
}

function formatMtime(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const Y = d.getFullYear();
  const M = String(d.getMonth() + 1).padStart(2, '0');
  const D = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  return `${Y}-${M}-${D} ${h}:${m}`;
}

function setSort(mode) {
  sortMode = mode;
  currentPage = 1;
  renderView();
}

/* ---- Pagination ---- */

function buildPagination(total) {
  const totalPages = Math.ceil(total / PAGE_SIZE);
  if (totalPages <= 1) return '';

  let html = '<div class="pagination">';
  html += `<button class="page-btn nav-arrow" ${currentPage <= 1 ? 'disabled' : ''} onclick="goPage(${currentPage - 1})">&lsaquo;</button>`;

  const pages = [];
  pages.push(1);
  let lo = Math.max(2, currentPage - 2);
  let hi = Math.min(totalPages - 1, currentPage + 2);
  if (lo > 2) pages.push('...');
  for (let p = lo; p <= hi; p++) pages.push(p);
  if (hi < totalPages - 1) pages.push('...');
  if (totalPages > 1) pages.push(totalPages);

  pages.forEach(p => {
    if (p === '...') {
      html += '<span class="page-ellipsis">…</span>';
    } else {
      html += `<button class="page-btn${p === currentPage ? ' active' : ''}" onclick="goPage(${p})">${p}</button>`;
    }
  });

  html += `<button class="page-btn nav-arrow" ${currentPage >= totalPages ? 'disabled' : ''} onclick="goPage(${currentPage + 1})">&rsaquo;</button>`;
  html += '</div>';
  return html;
}

function goPage(p) {
  const totalPages = Math.ceil(currentData.results.length / PAGE_SIZE);
  if (p < 1 || p > totalPages) return;
  currentPage = p;
  renderView();
  results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ---- Results ---- */

function renderView() {
  if (!currentData) {
    results.innerHTML = '<div class="no-results">没有找到相关文件，试试换个描述？</div>';
    return;
  }

  const sorted = getSortedResults(currentData.results);
  const total = sorted.length;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  if (currentPage > totalPages) currentPage = Math.max(1, totalPages);
  const start = (currentPage - 1) * PAGE_SIZE;
  const pageItems = sorted.slice(start, start + PAGE_SIZE);
  const q = currentData.query || '';

  let html = '<div class="results-toolbar">';
  html += `<div class="results-count">${total ? '找到 ' + total + ' 个相关结果' : '没有找到相关结果'}</div>`;
  html += '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:8px">';
  html += '<div class="sort-controls">';
  html += '<label>排序:</label>';
  html += `<button class="sort-btn${sortMode === 'relevance' ? ' active' : ''}" onclick="setSort('relevance')">匹配度</button>`;
  html += `<button class="sort-btn${sortMode === 'mtime_desc' ? ' active' : ''}" onclick="setSort('mtime_desc')">修改时间 ↓</button>`;
  html += `<button class="sort-btn${sortMode === 'mtime_asc' ? ' active' : ''}" onclick="setSort('mtime_asc')">修改时间 ↑</button>`;
  html += '</div>';
  html += '<div class="source-controls">';
  html += '<label>来源:</label>';
  html += `<button class="source-btn${sourceFilter === 'all' ? ' active' : ''}" onclick="setSource('all')">全部</button>`;
  html += `<button class="source-btn${sourceFilter === 'file' ? ' active' : ''}" onclick="setSource('file')">文件</button>`;
  if (ENABLE_MWEB) {
    html += `<button class="source-btn${sourceFilter === 'mweb' ? ' active' : ''}" onclick="setSource('mweb')">MWeb笔记</button>`;
  } else if (sourceFilter === 'mweb') {
    sourceFilter = 'file';
  }
  const hasDateFilter = dateRange !== 'all';
  html += `<button class="date-toggle-btn${hasDateFilter ? ' has-filter' : ''}" onclick="toggleDateFilter()">${hasDateFilter ? '<span class="dot"></span>' : ''}${dateFilterOpen ? '收起时间筛选' : '按时间筛选'}</button>`;
  html += '</div></div></div>';

  if (dateFilterOpen) {
    html += '<div class="date-filter-row">';
    html += '<label>依据:</label>';
    html += `<button class="date-btn${dateField === 'mtime' ? ' active' : ''}" onclick="setDateField('mtime')">修改时间</button>`;
    html += `<button class="date-btn${dateField === 'ctime' ? ' active' : ''}" onclick="setDateField('ctime')">创建时间</button>`;
    html += '<span style="color:var(--border);margin:0 4px">|</span>';
    html += '<label>范围:</label>';
    html += `<button class="date-btn${dateRange === 'all' ? ' active' : ''}" onclick="setDateRange('all')">全部</button>`;
    html += `<button class="date-btn${dateRange === 'week' ? ' active' : ''}" onclick="setDateRange('week')">最近一周</button>`;
    html += `<button class="date-btn${dateRange === 'month' ? ' active' : ''}" onclick="setDateRange('month')">最近一个月</button>`;
    html += `<button class="date-btn${dateRange === '3month' ? ' active' : ''}" onclick="setDateRange('3month')">最近三个月</button>`;
    html += `<button class="date-btn${dateRange === 'year' ? ' active' : ''}" onclick="setDateRange('year')">最近一年</button>`;
    html += `<button class="date-btn${dateRange === 'custom' ? ' active' : ''}" onclick="setDateRange('custom')">自定义</button>`;
    if (dateRange === 'custom') {
      const fmtFrom = dateFrom ? new Date(dateFrom * 1000).toISOString().slice(0, 10) : '';
      const fmtTo = dateTo ? new Date(dateTo * 1000).toISOString().slice(0, 10) : '';
      html += `<div class="date-custom-inputs">`;
      html += `<input type="date" id="dateFromInput" value="${fmtFrom}" onchange="applyCustomDate()">`;
      html += `<span>至</span>`;
      html += `<input type="date" id="dateToInput" value="${fmtTo}" onchange="applyCustomDate()">`;
      html += `</div>`;
    }
    html += '</div>';
  }

  if (!total) {
    html += '<div class="no-results">没有找到相关文件，试试换个描述或切换来源？</div>';
    results.innerHTML = html;
    return;
  }

  pageItems.forEach((r, idx) => {
    const [iconClass, iconLabel] = iconFor(r.filetype, r.source_type);
    const tagClass = r.tag === '精确匹配' ? 'keyword' : 'semantic';
    const tagText = r.tag === '精确匹配' ? '精确匹配' : r.relevance;
    const mtimeStr = formatMtime(r.mtime);
    const mwebBadge = r.source_type === 'mweb' ? '<span class="badge-mweb" title="MWeb 笔记">MWeb</span>' : '';
    const categoryLine = (r.source_type === 'mweb' && r.categories) ? `<div class="card-category">📂 ${esc(r.categories)}</div>` : '';
    const guessWantBadge = (smartSearchAvailable && (start + idx) === 0)
                           ? '<span class="badge-guess">猜你想找</span>' : '';
    html += `
      <div class="card">
        <div class="card-top">
          <div class="file-icon ${iconClass}">${iconLabel}</div>
          <div class="card-title">${highlight(r.filename, q)}${mwebBadge}${guessWantBadge}</div>
          <span class="tag ${tagClass}">${esc(tagText)}</span>
        </div>
        ${categoryLine}
        <div class="card-path">${highlight(shortenPath(r.filepath), q)}${mtimeStr ? ' &nbsp;·&nbsp; <span style="color:var(--text-secondary);font-size:11px">' + mtimeStr + '</span>' : ''}</div>
        <div class="card-preview">${highlight(r.preview, q)}</div>
        <div class="card-actions">
          <button class="btn-open" data-filepath="${esc(r.filepath)}" onclick="openFile(this.dataset.filepath)">打开</button>
          <button class="btn-reveal" data-filepath="${esc(r.filepath)}" onclick="reveal(this.dataset.filepath)">在 Finder 中显示</button>
        </div>
      </div>`;
  });

  if (totalPages > 1) {
    const rangeStart = start + 1;
    const rangeEnd = Math.min(start + PAGE_SIZE, total);
    html += `<div style="text-align:center;font-size:12px;color:var(--text-secondary);margin-top:16px;opacity:.7">第 ${rangeStart}-${rangeEnd} 条，共 ${total} 条</div>`;
    html += buildPagination(total);
  }

  results.innerHTML = html;
}

function renderResults(data) {
  currentData = data;
  sortMode = 'relevance';
  currentPage = 1;
  renderView();
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function highlight(text, query) {
  const safe = esc(text);
  if (!query) return safe;
  const tokens = query.split(/\s+/).filter(Boolean);
  const escaped = tokens.map(t => esc(t).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!escaped.length) return safe;
  const re = new RegExp('(' + escaped.join('|') + ')', 'gi');
  return safe.replace(re, '<mark>$1</mark>');
}

function setSearching(on) {
  searching = on;
  input.readOnly = on;
  searchProgress.classList.toggle('active', on);
  input.closest('.search-input-wrap').classList.toggle('loading', on);
  if (on) {
    if (submitBtn) {
      submitBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/></svg>';
    }
  } else {
    if (submitBtn) {
      submitBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>';
    }
  }
}

function cancelActiveSearch() {
  if (activeAbortCtrl) {
    activeAbortCtrl.abort();
    activeAbortCtrl = null;
  }
}

function createSearchSession() {
  cancelActiveSearch();
  activeSearchToken += 1;
  activeAbortCtrl = new AbortController();
  return {
    abortCtrl: activeAbortCtrl,
    token: activeSearchToken,
  };
}

function isActiveSearchSession(token, controller) {
  return token === activeSearchToken && controller === activeAbortCtrl && !controller.signal.aborted;
}

function abortSearch() {
  cancelActiveSearch();
  setSearching(false);
}

function matchDateRange(from, to) {
  if (!from && !to) return 'all';
  if (!to || to > Math.floor(Date.now() / 1000) - 86400) {
    const now = Math.floor(Date.now() / 1000);
    const DAY = 86400;
    const diff = now - from;
    if (Math.abs(diff - 7 * DAY) <= DAY * 2) return 'week';
    if (Math.abs(diff - 30 * DAY) <= DAY * 3) return 'month';
    if (Math.abs(diff - 90 * DAY) <= DAY * 5) return '3month';
    if (Math.abs(diff - 365 * DAY) <= DAY * 10) return 'year';
  }
  return 'custom';
}

function triggerSearch() {
  if (searching) { abortSearch(); return; }
  const q = input.value.trim();
  if (!q) return;
  searchMode = aiModeEnabled ? 'ai' : 'exact';
  doSearch(q);
}

async function startInterpretStream(userText, resultsList, token, controller) {
  interpretModule.style.display = 'block';
  interpretContent.innerHTML = '<span style="color:var(--text-secondary);font-size:13px">🤖 正在生成解读...</span>';
  try {
    const res = await fetch('/api/search/interpret/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_text: userText, results: resultsList }),
      signal: controller.signal
    });
    
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    
    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let contentHtml = "";
    interpretContent.innerHTML = "";
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!isActiveSearchSession(token, controller)) return;
      buffer += decoder.decode(value, { stream: true });
      let lines = buffer.split(/\r?\n/);
      buffer = lines.pop(); // keep remainder
      
      let eventType = null;
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.substring(7).trim();
        } else if (line.startsWith('data: ')) {
          const dataStr = line.substring(6).trim();
          if (dataStr) {
            let dataObj;
            try {
              dataObj = JSON.parse(dataStr);
            } catch(e) {
              console.warn("SSE 解读数据解析失败:", e, dataStr);
              continue;
            }
            if (eventType === 'error') {
              throw new Error(dataObj.error);
            } else if (dataObj.delta) {
              if (!isActiveSearchSession(token, controller)) return;
              contentHtml += esc(dataObj.delta);
              interpretContent.innerHTML = contentHtml.replace(/\n/g, '<br>');
            }
          }
        }
      }
    }
  } catch (e) {
    if (!isActiveSearchSession(token, controller) && e.name !== 'AbortError') return;
    if (e.name === 'AbortError') return;
    interpretModule.classList.add('error');
    interpretContent.innerHTML = '解读失败: ' + esc(e.message);
  }
}

async function doSearch(q) {
  const session = createSearchSession();
  const abortCtrl = session.abortCtrl;
  const searchToken = session.token;
  currentQuery = q;
  const introEl = document.getElementById('intro');
  if (introEl) {
    introEl.style.opacity = '0';
    setTimeout(() => { introEl.style.display = 'none'; }, 200);
  }
  results.innerHTML = '';
  interpretModule.style.display = 'none';
  interpretContent.innerHTML = '';
  interpretModule.classList.remove('error');
  setSearching(true);
  try {
    let data;
    if (searchMode === 'ai' && smartSearchAvailable) {
      const payload = {
        message: q,
        sidebar_source: sourceFilter,
        date_field: dateField,
        date_from: dateFrom,
        date_to: dateTo
      };
      const res = await fetch('/api/search/nl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: abortCtrl.signal
      });
      data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || ('HTTP ' + res.status + ' ' + res.statusText));
      }
      if (data.kind === 'capability_notice') {
        results.innerHTML = '<div class="no-results" style="text-align:left;">' +
          '<div style="font-weight:600;margin-bottom:8px;">⚠️ 无法处理该请求</div>' + 
          '<div style="margin-bottom:12px;">' + esc(data.message) + '</div>' +
          '<div style="font-size:12px;color:var(--text-secondary)">当前支持：' + esc(data.capabilities.join('、')) + '</div>' +
          '</div>';
        return;
      }
      
      // Update UI state to match resolved intents
      const resolved = data.resolved;
      if (resolved) {
        sourceFilter = resolved.source || 'all';
        dateField = resolved.date_field || 'mtime';
        dateFrom = resolved.date_from;
        dateTo = resolved.date_to;
        dateRange = matchDateRange(dateFrom, dateTo);
      }
      
    } else {
      let url = '/api/search?q=' + encodeURIComponent(q) + '&source=' + encodeURIComponent(sourceFilter) + '&date_field=' + encodeURIComponent(dateField) + '&exact_focus=true';
      if (dateFrom != null) url += '&date_from=' + dateFrom;
      if (dateTo != null) url += '&date_to=' + dateTo;
      const res = await fetch(url, { signal: abortCtrl.signal });
      data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const errMsg = (data && data.error) ? data.error : ('HTTP ' + res.status + ' ' + res.statusText);
        throw new Error(errMsg);
      }
    }

    renderResults(data);
    addToHistory(q, data.results?.length || 0);

    if (data.results && data.results.length > 0) {
      if (searchMode === 'ai' && smartSearchAvailable) {
        startInterpretStream(q, data.results, searchToken, abortCtrl);
      } else {
        // Fast local interpretation for exact keyword search
        interpretModule.style.display = 'block';
        interpretContent.innerHTML = '当前为关键字精确搜索，为您找到 ' + data.results.length + ' 条相关结果。若需根据语意进行模糊匹配，请尝试使用“AI 模式”搜索。';
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') return;
    const msg = (e && e.message) ? e.message : '未知错误';
    results.innerHTML = '<div class="no-results">搜索出错：' + esc(msg) + '</div>';
  } finally {
    if (searchToken === activeSearchToken) {
      setSearching(false);
    }
  }
}

async function openFile(fp) {
  if (!fp) return;
  const res = await fetch('/api/open', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({filepath: fp}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok && data.error) {
    alert(data.error);
  }
}

async function reveal(fp) {
  if (!fp) return;
  const res = await fetch('/api/reveal', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({filepath: fp}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok && data.error) {
    alert(data.error);
  }
}

if (submitBtn) {
  submitBtn.addEventListener('click', triggerSearch);
}
if (aiToggleBtn) {
  aiToggleBtn.addEventListener('click', (e) => {
    e.preventDefault();
    aiModeEnabled = !aiModeEnabled;
    aiToggleBtn.classList.toggle('active', aiModeEnabled);
  });
}

/* 仅回车或搜索按钮触发搜索，输入过程不做任何监控或动作 */
input.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    input.blur();
    return;
  }
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    triggerSearch();
  }
});

input.addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = (this.scrollHeight) + 'px';
  if(!this.value) { this.style.height = '52px'; }
});

const interpretModule = document.getElementById('interpretModule');
const interpretContent = document.getElementById('interpretContent');

document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    if (searching) return;
    input.focus();
    input.select();
  }
});

renderHistory();

/* ---- Intro text adjust ---- */
try {
  if (!ENABLE_MWEB) {
    const introNote = document.querySelector('.intro-item:nth-child(2) .intro-text');
    if (introNote) introNote.innerHTML = '<strong>本地文件</strong><br>仅检索本地文件内容与文件名（已关闭 MWeb 数据源）';
  }
} catch (_) {}
