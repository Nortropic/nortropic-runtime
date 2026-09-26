// The visitor's action grammar in JavaScript (D034). The holder imports this module; the host inlines the text between
// the two markers into every workspace's action command, so the command and the holder run the same functions. The
// Python side (runtime/web_common.py) applies the same grammar file; a test compares the two over one corpus.
// BEGIN NR GRAMMAR FUNCTIONS
function compileGrammar(grammar) {
  return Object.fromEntries(Object.entries(grammar.patterns).map(([k, v]) => [k, new RegExp(v, 'u')]));
}

function validateAction(argv, grammar, patterns) {
  if (!Array.isArray(argv) || argv.length === 0 || !argv.every((a) => typeof a === 'string')) throw new Error('ange en handling');
  const joined = argv.join(' ');
  if (argv.length > grammar.max_arguments || joined.length > grammar.max_argument_chars) throw new Error('för långt kommando');
  if (patterns.forbidden.test(joined)) throw new Error('argumenten innehåller otillåtna tecken');
  if (argv.some((a) => a === '' || a.includes(' '))) throw new Error('ogiltiga mellanrum');
  const [verb, ...rest] = argv;
  if (!Object.prototype.hasOwnProperty.call(grammar.verbs, verb)) throw new Error(`okänd handling; tillåtna: ${Object.keys(grammar.verbs).join(', ')}`);
  const shape = grammar.verbs[verb];
  if (shape.length === 0) {
    if (rest.length) throw new Error(`ogiltiga argument för ${verb}`);
    return [verb, []];
  }
  if (shape.length === 2 && shape[1] === 'text') {
    if (rest.length < 2 || !patterns.number.test(rest[0]) || !patterns.text.test(rest.slice(1).join(' '))) throw new Error(`ogiltiga argument för ${verb}`);
    return [verb, [rest[0], rest.slice(1).join(' ')]];
  }
  if (rest.length !== shape.length || !shape.every((kind, i) => patterns[kind].test(rest[i]))) throw new Error(`ogiltiga argument för ${verb}`);
  return [verb, rest];
}

function pageAllowed(url, allowed, grammar, patterns) {
  if (typeof url !== 'string' || !patterns.url.test(url)) return false;
  let u;
  try { u = new URL(url); } catch { return false; }
  if (!allowed.includes(u.origin) || u.search || u.hash) return false;
  const path = u.pathname || '/';
  if (grammar.page.denied_prefixes.some((p) => path === p || path.startsWith(p + '/'))) return false;
  const last = path.split('/').pop();
  const suffix = last.includes('.') ? '.' + last.split('.').pop().toLowerCase() : '';
  return grammar.page.allowed_suffixes.includes(suffix);
}
// END NR GRAMMAR FUNCTIONS

export { compileGrammar, validateAction, pageAllowed };
