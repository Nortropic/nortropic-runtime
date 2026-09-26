// The visitor's only way to act on the browser (D034). The host writes this file into the workspace as `handling`,
// with the node interpreter in its first line and the shared grammar inlined below; the visitor runs
// `./handling <action> [arguments]`. It needs no network and no dependency: it checks the action against the grammar,
// writes one request into the queue `.ko/` and waits for the holder's answer in `svar/`, which it cannot write.
// The holder applies the same grammar again and alone decides; this check only gives a readable refusal sooner.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const GRAMMAR = /*NR_GRAMMAR*/null;
const here = __dirname;

function refuse(message) {
  process.stdout.write(`FEL: ${message}\n`);
  process.exit(2);
}

const queue = path.join(here, '.ko');
const answers = path.join(here, 'svar');

/*NR_FUNCTIONS*/
const PATTERNS = compileGrammar(GRAMMAR);

function validate(argv) {
  try { validateAction(argv, GRAMMAR, PATTERNS); } catch (error) { refuse(error.message); }
}

const argv = process.argv.slice(2);
validate(argv);
const id = crypto.randomBytes(8).toString('hex');
const temporary = path.join(queue, `.${id}.tmp`);
try {
  fs.writeFileSync(temporary, JSON.stringify({ id, argv }), { flag: 'wx' });
  fs.renameSync(temporary, path.join(queue, `${id}.json`));
} catch (error) {
  refuse('kunde inte lämna begäran till webbläsaren');
}
const answerFile = path.join(answers, `${id}.json`);
const deadline = Date.now() + 90000;
const pause = new Int32Array(new SharedArrayBuffer(4));
while (Date.now() < deadline) {
  if (fs.existsSync(answerFile)) {
    let answer = null;
    try { answer = JSON.parse(fs.readFileSync(answerFile, 'utf8')); } catch { answer = null; }
    if (answer && answer.id === id) {
      process.stdout.write(String(answer.text) + '\n');
      process.exit(answer.code === 0 ? 0 : 2);
    }
  }
  Atomics.wait(pause, 0, 0, 100);
}
refuse('webbläsaren svarade inte inom 90 sekunder');
