'use strict';

// No browser, network, or database is used. Exercise the shipped game code with
// controllable clocks and delayed RPC responses so race conditions are repeatable.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };

function functionSource(name) {
  const match = new RegExp('(?:async )?function ' + name + '\\(').exec(html);
  assert.ok(match, name + ' exists');
  const start = match.index;
  let depth = 0, quote = '', escaped = false;
  for (let i = html.indexOf('{', start); i < html.length; i++) {
    const c = html[i];
    if (quote) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === quote) quote = '';
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; continue; }
    if (c === '{') depth++;
    if (c === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error('Unclosed function ' + name);
}

class Events {
  constructor() { this.listeners = {}; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  removeEventListener(type, callback) { this.listeners[type] = (this.listeners[type] || []).filter(x => x !== callback); }
  dispatchEvent(event) { event.target ||= this; for (const callback of this.listeners[event.type] || []) callback(event); }
  emit(type, extra = {}) { const event = { type, target: this, preventDefault() {}, ...extra }; this.dispatchEvent(event); return event; }
}

class Element extends Events {
  constructor(id = '', tag = 'DIV') {
    super(); this.id = id; this.tagName = tag; this.dataset = {}; this.hidden = false;
    this.disabled = false; this.value = ''; this.textContent = ''; this._html = '';
    this.clientWidth = 320; this.clientHeight = 290; this.offsetWidth = 100;
    this.style = { setProperty(key, value) { this[key] = value; } };
    const classes = new Set();
    this.classList = { add: (...xs) => xs.forEach(x => classes.add(x)), remove: (...xs) => xs.forEach(x => classes.delete(x)), contains: x => classes.has(x), toggle(x, on) { if (on === undefined) on = !classes.has(x); on ? classes.add(x) : classes.delete(x); } };
  }
  get innerHTML() { return this._html || this.textContent; }
  set innerHTML(value) { this._html = value; this.textContent = value; }
  closest(selector) {
    if (selector === 'section.art') return this.page || null;
    if (selector === '[data-game-panel]') return this.panel || null;
    if (selector === 'button' && this.tagName === 'BUTTON') return this;
    if (selector === '[data-polar-action]' && this.dataset.polarAction) return this;
    if (selector.includes('input,textarea') && (['INPUT', 'TEXTAREA', 'SELECT'].includes(this.tagName) || this.editable || this.dialog)) return this;
    if (selector === '.ox-choice' && this.dataset.ans) return this;
    return null;
  }
  focus() { this.focused = true; }
  appendChild(child) { child.parentNode = this; }
  removeChild(child) { child.parentNode = null; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
}

function clock() {
  let now = 0, next = 1;
  const tasks = new Map();
  function add(callback, delay, interval) { const id = next++; tasks.set(id, { callback, due: now + delay, interval }); return id; }
  return {
    tasks,
    setTimeout: (callback, delay = 0) => add(callback, delay, 0),
    clearTimeout: id => tasks.delete(id),
    setInterval: (callback, delay) => add(callback, delay, delay),
    clearInterval: id => tasks.delete(id),
    tick(ms) {
      const end = now + ms;
      let iterations = 0;
      while (true) {
        const due = [...tasks.entries()].filter(([, x]) => x.due <= end).sort((a, b) => a[1].due - b[1].due)[0];
        if (!due) break;
        assert.ok(iterations++ < 10000, 'timer loop terminates');
        const [id, task] = due; now = task.due;
        if (task.interval) task.due += task.interval; else tasks.delete(id);
        task.callback();
      }
      now = end;
    },
    get now() { return now; }
  };
}

function oxHarness(kind, options = {}) {
  const timers = clock(), document = new Events(), window = new Events(), nodes = new Map(), calls = [], scores = [];
  const page = new Element(); page.classList.add('on');
  const panel = new Element(); panel.page = page;
  const node = id => { if (!nodes.has(id)) nodes.set(id, new Element(id)); return nodes.get(id); };
  panel.querySelector = selector => node(selector.slice(1));
  document.querySelector = () => panel;
  document.getElementById = node;
  document.createElement = tag => new Element('', tag.toUpperCase());
  document.hidden = false;
  node(kind + 'Duration').value = '60'; node(kind + 'RevealMode').value = kind === 'ox' ? 'auto-10000' : 'auto';
  window.__addGameScore = (...args) => scores.push(args);
  window.LAWINUS_DB = { client: { rpc(name, args) {
    calls.push({ name, args });
    if (options.rpc) return options.rpc(name, args);
    if (name === 'get_private_game_questions') return Promise.resolve({ data: [{ question_id: 'q1', prompt: '테스트 문항', tags: '기출', grade: 'C', answer: 'O' }] });
    return Promise.resolve({ data: [{ answer: 'O', explanation: '테스트 해설' }] });
  } } };
  class FakeDate extends Date { constructor(...args) { super(...(args.length ? args : [timers.now])); } static now() { return timers.now; } }
  const context = vm.createContext({ window, document, console, Date: FakeDate, Math, Map, localStorage: { getItem() { return null; }, setItem() {} }, CustomEvent: class { constructor(type) { this.type = type; } }, ...timers });
  const helpersStart = html.indexOf('window.__lawinusGameVisible=');
  const helpersEnd = html.indexOf('(function(){', helpersStart);
  vm.runInContext(html.slice(helpersStart, helpersEnd), context);
  const start = html.indexOf('(function(){\n  var panel=document.querySelector(\'[data-game-panel="' + kind + '"]\');');
  const end = html.indexOf('\n})();', start) + '\n})();'.length;
  vm.runInContext(html.slice(start, end), context);
  return { timers, document, window, panel, page, node, calls, scores, start: () => node(kind + 'Start').emit('click'), stop: () => node(kind + 'Stop').emit('click'), key(key, target = panel, extra = {}) { document.emit('keydown', { key, target, ...extra }); } };
}

for (const kind of ['ox', 'ethics']) {
  test(kind + ': restarting keeps one round timer', async () => {
    const h = oxHarness(kind); h.start(); await flush(); h.start(); await flush();
    h.timers.tick(1000);
    assert.equal(h.node(kind + 'Time').textContent, 59);
    assert.equal([...h.timers.tasks.values()].filter(x => x.interval).length, 1);
  });

  test(kind + ': typing, modifiers, repeat, paused and hidden screens cannot submit O/X', async () => {
    const h = oxHarness(kind); h.start(); await flush();
    for (const tag of ['INPUT', 'TEXTAREA', 'SELECT']) h.key('o', new Element('', tag));
    h.key('o', h.panel, { isComposing: true }); h.key('o', h.panel, { repeat: true }); h.key('o', h.panel, { ctrlKey: true });
    h.node(kind + 'Pause').emit('click'); h.key('o');
    const choice = new Element(); choice.dataset.ans = 'O'; h.node(kind + 'Buttons').emit('click', { target: choice });
    h.node(kind + 'Pause').emit('click'); h.page.classList.remove('on'); h.key('o');
    assert.equal(h.calls.filter(x => x.name === 'grade_private_game_question').length, 0);
    h.page.classList.add('on'); h.key('o'); await flush();
    assert.equal(h.calls.filter(x => x.name === 'grade_private_game_question').length, 1);
  });

  test(kind + ': late grading after stop cannot alter result or save again', async () => {
    const grading = deferred();
    const h = oxHarness(kind, { rpc(name) { return name === 'get_private_game_questions' ? Promise.resolve({ data: [{ question_id: 'q1', prompt: '테스트 문항' }] }) : grading.promise; } });
    h.start(); await flush(); h.key('o'); h.stop();
    const result = h.node(kind + 'Target').textContent;
    grading.resolve({ data: [{ answer: 'O' }] }); await flush(); h.stop();
    assert.equal(h.node(kind + 'Target').textContent, result);
    assert.equal(h.node(kind + 'Acc').textContent, '0/0');
    assert.equal(h.scores.length, 0);
  });

  test(kind + ': stopping while loading cancels the pending start', async () => {
    const loading = deferred(), h = oxHarness(kind, { rpc: () => loading.promise });
    h.start(); h.stop(); loading.resolve({ data: [{ question_id: 'q1', prompt: '테스트 문항' }] }); await flush();
    assert.equal(h.timers.tasks.size, 0);
    h.key('o'); assert.equal(h.calls.length, 1);
  });

  test(kind + ': only latest overlapping start response can activate a round', async () => {
    const first = deferred(), second = deferred(); let i = 0;
    const h = oxHarness(kind, { rpc: () => (++i === 1 ? first : second).promise });
    h.start(); h.start(); second.resolve({ data: [{ question_id: 'new', prompt: '새 라운드 문항' }] }); await flush();
    first.resolve({ data: [{ question_id: 'old', prompt: '이전 라운드 문항' }] }); await flush();
    assert.match(h.node(kind + 'Target').textContent, /새 라운드 문항/);
    assert.equal([...h.timers.tasks.values()].filter(x => x.interval).length, 1);
  });

  test(kind + ': leaving the game pauses its timer', async () => {
    const h = oxHarness(kind); h.start(); await flush(); h.panel.hidden = true;
    h.document.emit('lawinus-game-mode-change'); h.timers.tick(25000);
    assert.equal(h.node(kind + 'Time').textContent, 60);
    assert.equal(h.calls.filter(x => x.name === 'grade_private_game_question').length, 0);
  });
}

test('ethics: hidden explanations still advance after grading', async () => {
  const h = oxHarness('ethics'); h.node('ethicsRevealMode').value = 'none';
  h.start(); await flush(); h.key('o'); await flush(); h.timers.tick(600);
  assert.equal(h.node('ethicsButtons').hidden, false);
});

function caseHarness() {
  const timers = clock(), requests = [], scores = [], nodes = {};
  for (const name of ['caseInput', 'caseQuestion', 'caseArticle', 'caseFeed', 'caseReportBtn']) nodes[name] = new Element(name);
  const round = () => ({ active: true, current: null, loading: false, score: 0, combo: 0, ok: 0, bad: 0, used: {}, time: 30 });
  const context = vm.createContext({ console, ...timers, ...nodes, caseblank: round(), caseWrongTimer: null, caseRequestVersion: 0, caseEnterLock: false,
    fetchCaseQuestion() { const request = deferred(); requests.push(request); return request.promise; },
    gameVisible: () => true, getBank: () => ({ caseBlanks: [{ question: '대체 문항', answer: '대체', article: '대체 출처' }] }), pick: list => list[0],
    caseStats() {}, renderCaseQuestion(q) { nodes.caseQuestion.textContent = q; }, norm: s => s.trim(), answerMatches: (a, b) => a === b,
    addCaseTimeBonus: () => 1, esc: s => s, addScore: (...args) => scores.push(args), gameAdjustedScore: x => x,
    document: { getElementById: () => ({ value: '' }) }
  });
  for (const name of ['nextCaseBlank', 'submitCaseBlank', 'finishCaseBlank']) vm.runInContext(functionSource(name), context);
  return { context, requests, scores, timers, nodes, round };
}

test('case blank: loading clears old answer and repeated Enter cannot score it twice', async () => {
  const h = caseHarness(), c = h.context;
  c.caseblank.current = { answer: '정답', question: '첫 문항', article: '출처' };
  h.nodes.caseInput.value = '정답'; c.submitCaseBlank(); c.submitCaseBlank();
  assert.equal(c.caseblank.ok, 1); assert.equal(c.caseblank.current, null); assert.equal(h.requests.length, 1);
  h.requests[0].resolve({ answer: '다음', question: '다음 문항', article: '출처' }); await flush();
  assert.equal(c.caseblank.current.answer, '다음'); assert.equal(h.nodes.caseInput.disabled, false);
});

test('case blank: response from previous round cannot replace current round', async () => {
  const h = caseHarness(), c = h.context;
  c.nextCaseBlank(); c.caseblank = h.round(); c.nextCaseBlank();
  h.requests[1].resolve({ answer: '새 정답', question: '새 문항', article: '출처' }); await flush();
  h.requests[0].resolve({ answer: '옛 정답', question: '옛 문항', article: '출처' }); await flush();
  assert.equal(c.caseblank.current.answer, '새 정답');
});

test('case blank: repeated wrong answer is counted once during feedback', () => {
  const h = caseHarness(); h.context.caseblank.current = { answer: '정답' }; h.nodes.caseInput.value = '오답';
  h.context.submitCaseBlank(); h.context.submitCaseBlank();
  assert.equal(h.context.caseblank.bad, 1);
});

test('case blank: stop clears delayed feedback and saves a round once', async () => {
  const h = caseHarness(); h.context.caseblank.current = { answer: '정답' }; h.nodes.caseInput.value = '오답';
  h.context.submitCaseBlank(); h.context.finishCaseBlank('force'); h.context.finishCaseBlank('force'); h.timers.tick(1000);
  assert.equal(h.scores.length, 1); assert.equal(h.requests.length, 0);
});

test('all main games: already stopped rounds cannot create another score', () => {
  for (const [name, state, args] of [['finishTyping', 'typing', ['force']], ['finishBlank', 'blank', ['force']], ['finishCaseBlank', 'caseblank', ['force']], ['finishRain', 'rain', [true]], ['finishPolar', 'polar', [false, '', true]]]) {
    const context = vm.createContext({ [state]: { active: false, transition: false }, addScore() { assert.fail(name + ' saved twice'); } });
    vm.runInContext(functionSource(name), context); context[name](...args);
  }
});

test('polar: left and right objects stay inside narrow and resized game boards', () => {
  const stage = new Element();
  const context = vm.createContext({ polarStage: stage, Math, polarY: d => 56 + d * 200 });
  vm.runInContext(functionSource('polarLaneX') + '\n' + functionSource('updatePolarObject'), context);
  for (const width of [220, 264, 320, 360, 640, 1000, 264]) {
    stage.clientWidth = width;
    for (const lane of [-1, 0, 1]) for (const d of [0, .5, 1, 1.12]) {
      const el = new Element(); el.offsetWidth = 110;
      context.updatePolarObject({ kind: 'flag', lane, d, el });
      const x = Number.parseFloat(el.style.left), half = el.offsetWidth * el.style['--s'] / 2;
      assert.ok(x - half >= 7.99 && x + half <= width - 7.99, `width ${width}, lane ${lane}, depth ${d}`);
    }
  }
});

async function centerHarness() {
  const timers = clock(), document = new Events(), window = new Events(), nodes = new Map(), panels = new Map();
  const page = new Element(); page.classList.add('on');
  const root = new Element('gameCenter');
  const node = id => { if (!nodes.has(id)) nodes.set(id, new Element(id)); return nodes.get(id); };
  for (const mode of ['typing', 'rain', 'blank', 'caseblank', 'polar']) { const panel = new Element(mode); panel.page = page; panels.set(mode, panel); }
  root.querySelector = selector => panels.get((selector.match(/data-game-panel="([^"]+)/) || [])[1]) || null;
  nodes.set('gameCenter', root);
  document.getElementById = node; document.querySelectorAll = () => [];
  document.createElement = tag => new Element('', tag.toUpperCase());
  for (const prefix of ['typing', 'rain', 'blank', 'case', 'polar']) node(prefix + 'Duration').value = '30';
  node('typingBank').value = 'terms'; node('rainLevel').value = '0';
  node('polarStage').panel = panels.get('polar');
  const polarButtons = ['left', 'jump', 'right'].map(action => {
    const button = new Element('polar-' + action, 'BUTTON'); button.dataset.polarAction = action; button.disabled = true; return button;
  });
  node('polarControls').querySelectorAll = () => polarButtons;
  const storage = new Map();
  const context = vm.createContext({ window, document, console, Math, Date, CustomEvent: class { constructor(type) { this.type = type; } },
    localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
    loadExamTerms: async () => ({ all: ['소멸시효', '기판력'], civil: [], criminal: [], public: [] }),
    loadObjectiveAtomStatements: async () => [], fetchCaseQuestion: async () => ({ answer: '정답', question: '테스트 문항', article: '출처' }),
    esc: s => s, fmt: () => '', requestAnimationFrame: () => 999, cancelAnimationFrame() {},
    performance: { now: () => timers.now }, navigator: {}, ...timers });
  const helperStart = html.indexOf('window.__lawinusGameVisible=');
  vm.runInContext(html.slice(helperStart, html.indexOf('(function(){', helperStart)), context);
  const start = html.indexOf('  async function initGameCenter(){');
  const end = html.indexOf('\n  initGameCenter();', start);
  vm.runInContext(html.slice(start, end), context);
  await context.initGameCenter(); await flush();
  return { timers, document, window, node, panels, page, polarButtons };
}

test('main game timers freeze when their panel is hidden, then resume', async () => {
  const h = await centerHarness();
  for (const [mode, prefix] of [['typing', 'typing'], ['blank', 'blank'], ['caseblank', 'case']]) {
    h.node(prefix + 'Start').emit('click'); await flush(); h.timers.tick(1000);
    assert.equal(h.node(prefix + 'Time').textContent, 29, mode);
    h.panels.get(mode).hidden = true; h.timers.tick(5000);
    assert.equal(h.node(prefix + 'Time').textContent, 29, mode + ' remains paused');
    h.panels.get(mode).hidden = false; h.timers.tick(1000);
    assert.equal(h.node(prefix + 'Time').textContent, 28, mode + ' resumes');
    h.panels.get(mode).hidden = true;
  }
});

test('blank: an old round IME callback cannot unlock a new pending answer', async () => {
  const h = await centerHarness(), input = h.node('blankInput');
  h.node('blankStart').emit('click'); input.value = '소멸시효'; input.emit('keydown', { key: 'Enter' });
  h.timers.tick(10);
  h.node('blankStart').emit('click'); input.value = '소멸시효'; input.emit('keydown', { key: 'Enter' });
  h.timers.tick(35); // The previous round's delayed callback is now due.
  input.emit('keydown', { key: 'Enter' }); // Must remain locked by the new round.
  h.timers.tick(45);
  assert.equal(h.node('blankSolved').textContent, 1);
  assert.match(h.node('blankFeed').textContent, /^정답!/);
});

test('polar: visible control handlers move and jump only during a visible active game', async () => {
  const h = await centerHarness(), [left, jump, right] = h.polarButtons;
  const click = button => h.node('polarControls').emit('click', { target: button });
  click(left); assert.equal(h.node('polarPlayer').style.left, undefined);
  h.node('polarStart').emit('click');
  assert.ok(h.polarButtons.every(button => !button.disabled));
  click(left); assert.equal(h.node('polarPlayer').style.left, '25%');
  click(right); assert.equal(h.node('polarPlayer').style.left, '50%');
  click(jump); assert.ok(h.node('polarPlayer').classList.contains('jump'));
  h.panels.get('polar').hidden = true; click(right);
  assert.equal(h.node('polarPlayer').style.left, '50%');
  h.panels.get('polar').hidden = false; h.node('polarStop').emit('click'); click(right);
  assert.equal(h.node('polarPlayer').style.left, '50%');
  assert.ok(h.polarButtons.every(button => button.disabled));
});

test('polar: Space and Enter on control buttons use native click without a second document action', async () => {
  const h = await centerHarness(), [, , right] = h.polarButtons;
  h.node('polarStart').emit('click');
  h.document.emit('keydown', { key: ' ', target: right });
  assert.equal(h.node('polarPlayer').classList.contains('jump'), false);
  h.node('polarControls').emit('click', { target: right });
  assert.equal(h.node('polarPlayer').style.left, '75%');
  h.document.emit('keydown', { key: 'Enter', target: h.polarButtons[0] });
  h.node('polarControls').emit('click', { target: h.polarButtons[0] });
  assert.equal(h.node('polarPlayer').style.left, '50%');
  assert.equal(h.node('polarPlayer').classList.contains('jump'), false);
});
