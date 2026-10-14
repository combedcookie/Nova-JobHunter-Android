const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync(
  'app/src/main/assets/index.html', 'utf8'
);

function extract(name) {
  const start = html.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `Missing ${name}`);

  const open = html.indexOf('{', start);
  let depth = 0, quote = '', escaped = false;

  for (let i = open; i < html.length; i++) {
    const c = html[i];

    if (quote) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === quote) quote = '';
      continue;
    }

    if (c === '"' || c === "'" || c === '`') {
      quote = c;
      continue;
    }

    if (c === '{') depth++;
    if (c === '}') {
      depth--;
      if (depth === 0) return html.slice(start, i + 1);
    }
  }
  throw Error(`Unclosed function ${name}`);
}

function environment() {
  const calls = [];
  const field = { value: '' };
  const ctx = {
    novaAiRequest: 1,
    novaAiBusy: true,
    novaAiCancelRequested: false,
    novaAiStalled: false,
    novaDebugPending: null,
    novaDebugRuns: [],
    novaAiMessages: [],
    novaUnifiedNext: '',
    hqMeetingActive: false,
    hqMeetingTurns: 0,
    hqSpeaker: 'NOVA',
    hqChannel: 'meeting',
    hqDiscussion: {
      active: true,
      topic: 'Architecture review',
      limit: 4,
      turns: 0,
      stopRequested: false,
      resolving: false,
      startIndex: 0,
      ownerQueue: [],
      lastOwnerInput: ''
    },
    window: {},
    document: {
      getElementById: id => id === 'novaAiInput' ? field : null
    },
    Nova: {
      novaGenerate(prompt, id) {
        calls.push({ prompt, id });
      }
    },
    novaAiStopWatchdog() {},
    novaAiWatch() {},
    novaCleanAnswer: x => String(x || '').trim(),
    hqSave() {},
    show() {},
    hqDiscussionPrompt(speaker) {
      return `${speaker}\n${ctx.hqDiscussion.lastOwnerInput}\n` +
        `Final: ${ctx.hqDiscussion.resolving}`;
    }
  };

  vm.createContext(ctx);
  vm.runInContext(
    extract('novaAiSend') + '\n' +
    extract('novaAiResult'),
    ctx
  );

  return {
    ctx, calls, field,
    respond(text, ok = true) {
      ctx.novaAiResult(ctx.novaAiRequest, ok, text);
    },
    send(text) {
      field.value = text;
      ctx.novaAiSend();
    }
  };
}

test('owner messages queue without interrupting current agent', () => {
  const e = environment();

  e.send('Check privacy');
  e.send('Keep everything offline');

  assert.equal(e.ctx.hqDiscussion.ownerQueue.length, 2);
  assert.equal(e.calls.length, 0);
  assert.equal(e.ctx.novaAiMessages.length, 2);

  e.respond('NOVA analysis');

  assert.equal(e.calls.length, 1);
  assert.match(e.calls[0].prompt, /Check privacy/);
  assert.match(e.calls[0].prompt, /Keep everything offline/);
  assert.equal(e.ctx.hqDiscussion.ownerQueue.length, 0);
});

test('discussion alternates agents and ends with NOVA', () => {
  const e = environment();

  e.respond('NOVA opening');
  assert.equal(e.ctx.hqSpeaker, 'ECLIPSE');

  e.respond('Eclipse challenge');
  assert.equal(e.ctx.hqSpeaker, 'NOVA');

  e.respond('NOVA revision');
  assert.equal(e.ctx.hqSpeaker, 'ECLIPSE');

  e.respond('Eclipse conclusion');
  assert.equal(e.ctx.hqSpeaker, 'NOVA');
  assert.equal(e.ctx.hqDiscussion.resolving, true);

  e.respond('NOVA final resolution');
  assert.equal(e.ctx.hqDiscussion.active, false);
});

test('owner message during final resolution gets answered', () => {
  const e = environment();

  for (let i = 0; i < 4; i++) e.respond(`Agent turn ${i}`);
  assert.equal(e.ctx.hqDiscussion.resolving, true);

  e.send('What about battery usage?');
  e.respond('NOVA initial resolution');

  assert.equal(e.ctx.hqDiscussion.active, true);
  assert.match(e.calls.at(-1).prompt, /battery usage/);

  e.respond('NOVA battery follow-up');
  assert.equal(e.ctx.hqDiscussion.active, false);
});

test('stopped discussion ignores late callback', () => {
  const e = environment();

  e.ctx.hqDiscussion.stopRequested = true;
  e.ctx.hqDiscussion.ownerQueue.push('Discard');

  const before = e.ctx.novaAiMessages.length;
  e.respond('Late native response');

  assert.equal(e.ctx.hqDiscussion.active, false);
  assert.equal(e.ctx.hqDiscussion.ownerQueue.length, 0);
  assert.equal(e.ctx.novaAiMessages.length, before);
  assert.equal(e.calls.length, 0);
});

test('ordinary chat remains gated while generation is busy', () => {
  const e = environment();
  e.ctx.hqDiscussion.active = false;

  e.send('Ordinary chat message');

  assert.equal(e.ctx.novaAiMessages.length, 0);
  assert.equal(e.calls.length, 0);
});
