#!/usr/bin/env bun
/**
 * List the e2e coverage targets of a SvelteKit app, and pick the e2e cases a change touches.
 *
 *   bun .claude/bin/e2e-inventory-sveltekit.ts write  [--out e2e/ledger/inventory.json]
 *   bun .claude/bin/e2e-inventory-sveltekit.ts check  [--out e2e/ledger/inventory.json]
 *   bun .claude/bin/e2e-inventory-sveltekit.ts select --base <ref> [--ledger e2e/ledger] [--tests e2e]
 *
 * Run it from the repository root. It reads src/ with the project's own `svelte/compiler`
 * and `typescript`. What it extracts, and how the ledger uses it, is defined in
 * .claude/references/verification-map.md. Exit codes: 0 ok, 1 inventory out of date, 2 could not run.
 */
import { parse } from 'svelte/compiler';
import * as ts from 'typescript';

// Module-scoped declarations of the Bun APIs used here, so the project needs no @types/bun.
declare const Bun: {
	argv: string[];
	file(path: string): { text(): Promise<string> };
	write(path: string, data: string): Promise<number>;
	spawnSync(cmd: string[], options: { stdout: 'pipe'; stderr: 'pipe' }): { exitCode: number; stdout: Uint8Array; stderr: Uint8Array };
	Glob: new (pattern: string) => { scanSync(options: { cwd: string }): Iterable<string> };
};
declare const process: { exitCode: number | undefined };

type Kind = 'route' | 'api' | 'action' | 'ui' | 'call' | 'link' | 'unresolved';
type Item = { key: string; kind: Kind; source: string; line: number; reason?: string };
type Node = { type?: string; start?: number; [k: string]: unknown };

const METHODS = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'fallback'];
const FORM_ELEMENTS = ['input', 'select', 'textarea'];
const FORM_BINDINGS = ['value', 'checked', 'group', 'files'];
const PAGE_FILE = /^\+page(@.*)?\.svelte$/;
const SERVER_FILE = /^\+server\.(ts|js)$/;
const PAGE_SERVER_FILE = /^\+page\.server\.(ts|js)$/;
const TEST_FILE = /\.(test|spec)\.(ts|js)$|\.d\.ts$/;

class CannotRun extends Error {}

const basename = (p: string) => p.slice(p.lastIndexOf('/') + 1);
const dirname = (p: string) => p.slice(0, Math.max(p.lastIndexOf('/'), 0));

function normalize(p: string): string {
	const out: string[] = [];
	for (const part of p.split('/')) {
		if (part === '..') out.pop();
		else if (part !== '.' && part !== '') out.push(part);
	}
	return out.join('/');
}

function routePath(file: string): string {
	// Groups like (app) do not appear in the URL; parameters stay as written.
	const parts = dirname(file)
		.slice('src/routes'.length)
		.split('/')
		.filter((p) => p && !(p.startsWith('(') && p.endsWith(')')));
	return '/' + parts.join('/');
}

function isServerOnly(file: string): boolean {
	return file.startsWith('src/lib/server/') || /\.server\.(ts|js)$/.test(file) || SERVER_FILE.test(basename(file));
}

/**
 * A static URL from string parts (split at each interpolation); null if not internal.
 * Links keep `[param]` for an interpolated segment; API calls must have a static path.
 */
function internalPath(parts: string[], params: boolean): string | 'unresolved' | null {
	const joined = parts.join('\u0000');
	if (/^(https?:|\/\/|mailto:|tel:|#)/.test(joined)) return null;
	const path = joined.split(/[?#]/)[0];
	if (!path.startsWith('/') || (!params && path.includes('\u0000'))) return 'unresolved';
	return path.replaceAll('\u0000', '[param]');
}

/** Returns offset -> 1-based line, by binary search over the line starts of `text`. */
function lineFinder(text: string): (offset: number) => number {
	const starts = [0];
	for (let i = 0; i < text.length; i++) if (text.charCodeAt(i) === 10) starts.push(i + 1);
	return (offset) => {
		let lo = 0;
		let hi = starts.length - 1;
		while (lo < hi) {
			const mid = (lo + hi + 1) >> 1;
			if (starts[mid] <= offset) lo = mid;
			else hi = mid - 1;
		}
		return lo + 1;
	};
}

class Collector {
	items: Item[] = [];
	imports = new Map<string, string[]>();
	add(item: Item) {
		this.items.push(item);
	}
	unresolved(source: string, line: number, what: string, reason: string) {
		this.add({ key: `unresolved:${source}#${what}`, kind: 'unresolved', source, line, reason });
	}
}

function callTarget(
	c: Collector,
	file: string,
	line: number,
	callee: string,
	urlParts: string[] | null,
	argText: string,
	method: string | null
) {
	const path = urlParts ? internalPath(urlParts, callee === 'goto') : 'unresolved';
	if (path === null) return;
	if (path === 'unresolved' || method === null) {
		c.unresolved(file, line, `${callee}(${argText.slice(0, 60)})`, '宛先かメソッドが静的に決まらない');
	} else if (callee === 'fetch') {
		c.add({ key: `call:${file}#${method} ${path}`, kind: 'call', source: file, line });
	} else {
		c.add({ key: `link:${file}#${path}`, kind: 'link', source: file, line });
	}
}

// --- Svelte components -------------------------------------------------------

function staticValue(attr: Node | undefined): string | null {
	const value = attr?.value;
	if (!Array.isArray(value) || value.length !== 1 || (value[0] as Node).type !== 'Text') return null;
	return String((value[0] as Node).data).trim() || null;
}

function firstText(node: Node): string | null {
	const nodes = (node.fragment as { nodes?: Node[] } | undefined)?.nodes ?? [];
	for (const child of nodes) {
		if (child.type === 'Text' && String(child.data).trim()) return String(child.data).trim();
		if (child.type === 'RegularElement') {
			const found = firstText(child);
			if (found) return found;
		}
	}
	return null;
}

function elementName(node: Node, ancestors: Node[]): string | null {
	const attrs = (node.attributes as Node[]) ?? [];
	for (const name of ['aria-label', 'id', 'name']) {
		const found = staticValue(attrs.find((a) => a.type === 'Attribute' && a.name === name));
		if (found) return found;
	}
	if (node.type !== 'RegularElement') return null;
	const own = firstText(node);
	if (own) return own;
	const label = [...ancestors].reverse().find((a) => a.type === 'RegularElement' && a.name === 'label');
	return label ? firstText(label) : null;
}

function estreeUrl(arg: Node | undefined): string[] | null {
	if (arg?.type === 'Literal' && typeof arg.value === 'string') return [arg.value];
	if (arg?.type === 'TemplateLiteral') {
		return (arg.quasis as Node[]).map((q) => String((q.value as { cooked: string }).cooked));
	}
	return null;
}

function estreeMethod(arg: Node | undefined): string | null {
	if (!arg) return 'GET';
	if (arg.type !== 'ObjectExpression') return null;
	for (const p of arg.properties as Node[]) {
		if (p.type === 'SpreadElement') return null;
		const key = p.key as Node;
		if (p.type === 'Property' && (key.name === 'method' || key.value === 'method')) {
			const v = p.value as Node;
			return v.type === 'Literal' && typeof v.value === 'string' ? v.value.toUpperCase() : null;
		}
	}
	return 'GET';
}

function extractSvelte(c: Collector, file: string, text: string) {
	let ast: Node;
	try {
		ast = parse(text, { filename: file, modern: true }) as unknown as Node;
	} catch (e) {
		throw new CannotRun(`${file} を解析できない: ${(e as Error).message}`);
	}
	const ui: { element: string; name: string | null; event: string; line: number }[] = [];
	const imports: string[] = [];
	const seen = new WeakSet<object>();
	const lineOf = lineFinder(text);

	const visit = (node: Node, ancestors: Node[]) => {
		if (seen.has(node)) return;
		seen.add(node);
		const line = lineOf(node.start ?? 0);
		if (typeof node.name === 'string' && Array.isArray(node.attributes)) {
			const element = node.name;
			for (const attr of node.attributes as Node[]) {
				let event: string | null = null;
				if (attr.type === 'Attribute' && (node.type === 'RegularElement' ? /^on[a-z]+$/ : /^on[a-zA-Z]+$/).test(String(attr.name)) && attr.value !== true)
					event = String(attr.name);
				else if (attr.type === 'OnDirective') event = `on:${attr.name}`;
				else if (
					attr.type === 'BindDirective' &&
					node.type === 'RegularElement' &&
					FORM_ELEMENTS.includes(element) &&
					FORM_BINDINGS.includes(String(attr.name))
				)
					event = `bind:${attr.name}`;
				else if (attr.type === 'SpreadAttribute' && node.type === 'RegularElement') {
					c.unresolved(file, line, `${element}.spread`, '要素へのスプレッドは、中の操作を数えられない');
				}
				if (event) ui.push({ element, name: elementName(node, ancestors), event, line });
			}
			if (node.type === 'RegularElement' && element === 'a') {
				const href = (node.attributes as Node[]).find((a) => a.type === 'Attribute' && a.name === 'href');
				if (href && href.value !== true && !Array.isArray(href.value)) {
					c.unresolved(file, line, 'a(href)', 'リンク先が静的に決まらない');
				} else if (href && Array.isArray(href.value)) {
					const parts = [''];
					for (const v of href.value as Node[]) {
						if (v.type === 'Text') parts[parts.length - 1] += String(v.data);
						else parts.push('');
					}
					const path = internalPath(parts, true);
					if (path === 'unresolved') c.unresolved(file, line, `a(href)`, 'リンク先が静的に決まらない');
					else if (path !== null) c.add({ key: `link:${file}#${path}`, kind: 'link', source: file, line });
				}
			}
		}
		if (node.type === 'CallExpression') {
			const callee = node.callee as Node;
			if (callee.type === 'Identifier' && (callee.name === 'fetch' || callee.name === 'goto')) {
				const args = node.arguments as Node[];
				const argText = args[0] ? text.slice(args[0].start, args[0].end as number) : '';
				const method = callee.name === 'fetch' ? estreeMethod(args[1]) : 'GET';
				callTarget(c, file, line, callee.name, estreeUrl(args[0]), argText, method);
			}
		}
		if (node.type === 'ImportDeclaration' || ((node.type === 'ExportNamedDeclaration' || node.type === 'ExportAllDeclaration') && node.source)) {
			imports.push(String((node.source as Node).value));
		}
		if (node.type === 'ImportExpression' && (node.source as Node).type === 'Literal') {
			imports.push(String((node.source as Node).value));
		}
		const next = [...ancestors, node];
		for (const [k, v] of Object.entries(node)) {
			if (k === 'parent' || k === 'metadata') continue;
			if (Array.isArray(v)) for (const x of v) if (x && typeof x === 'object') visit(x as Node, next);
			if (v && typeof v === 'object' && !Array.isArray(v)) visit(v as Node, next);
		}
	};
	visit(ast, []);

	const byKey = new Map<string, typeof ui>();
	for (const u of ui) {
		const key = `ui:${file}#${u.element}${u.name ? `[${u.name}]` : ''}.${u.event}`;
		byKey.set(key, [...(byKey.get(key) ?? []), u]);
	}
	for (const [key, uses] of byKey) {
		if (uses.length === 1) c.add({ key, kind: 'ui', source: file, line: uses[0].line });
		else
			c.unresolved(
				file,
				uses[0].line,
				`${uses[0].element}.${uses[0].event}`,
				`同じ要素・同じ操作が${uses.length}か所あり、名前で区別できない（aria-labelなどを付ける）`
			);
	}
	c.imports.set(file, imports);
}

// --- TypeScript modules ------------------------------------------------------

function tsUrl(arg: ts.Expression | undefined): string[] | null {
	if (!arg) return null;
	if (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg)) return [arg.text];
	if (ts.isTemplateExpression(arg)) return [arg.head.text, ...arg.templateSpans.map((s) => s.literal.text)];
	return null;
}

function tsMethod(arg: ts.Expression | undefined): string | null {
	if (!arg) return 'GET';
	if (!ts.isObjectLiteralExpression(arg)) return null;
	for (const p of arg.properties) {
		if (ts.isSpreadAssignment(p)) return null;
		const name = p.name && (ts.isIdentifier(p.name) || ts.isStringLiteralLike(p.name)) ? p.name.text : null;
		if (name !== 'method') continue;
		return ts.isPropertyAssignment(p) && ts.isStringLiteralLike(p.initializer) ? p.initializer.text.toUpperCase() : null;
	}
	return 'GET';
}

function exportedNames(sf: ts.SourceFile): Map<string, ts.Node> {
	const names = new Map<string, ts.Node>();
	for (const st of sf.statements) {
		const exported = ts.canHaveModifiers(st) && ts.getModifiers(st)?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword);
		if (exported && ts.isFunctionDeclaration(st) && st.name) names.set(st.name.text, st);
		if (exported && ts.isVariableStatement(st)) {
			for (const d of st.declarationList.declarations) if (ts.isIdentifier(d.name)) names.set(d.name.text, d);
		}
		if (ts.isExportDeclaration(st) && st.exportClause && ts.isNamedExports(st.exportClause)) {
			for (const e of st.exportClause.elements) names.set(e.name.text, e);
		}
	}
	return names;
}

function extractModule(c: Collector, file: string, text: string) {
	const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
	const line = (n: ts.Node) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
	const name = basename(file);

	if (file.startsWith('src/routes/') && SERVER_FILE.test(name)) {
		const methods = [...exportedNames(sf).entries()].filter(([n]) => METHODS.includes(n));
		if (methods.length === 0) c.unresolved(file, 1, 'methods', 'HTTPメソッドの書き出しが見つからない');
		for (const [m, n] of methods) c.add({ key: `api:${m} ${routePath(file)}`, kind: 'api', source: file, line: line(n) });
	}
	if (file.startsWith('src/routes/') && PAGE_SERVER_FILE.test(name)) {
		const actions = exportedNames(sf).get('actions');
		if (actions) {
			const init = ts.isVariableDeclaration(actions) ? actions.initializer : undefined;
			const obj = init && ts.isSatisfiesExpression(init) ? init.expression : init;
			if (!obj || !ts.isObjectLiteralExpression(obj) || obj.properties.some((p) => ts.isSpreadAssignment(p))) {
				c.unresolved(file, line(actions), 'actions', 'actionsの名前が静的に決まらない');
			} else {
				for (const p of obj.properties) {
					const n = p.name?.getText(sf).replace(/^['"]|['"]$/g, '');
					const target = n === 'default' ? routePath(file) : `${routePath(file)}?/${n}`;
					c.add({ key: `action:${target}`, kind: 'action', source: file, line: line(p) });
				}
			}
		}
	}

	const imports: string[] = [];
	const visit = (n: ts.Node) => {
		if ((ts.isImportDeclaration(n) || ts.isExportDeclaration(n)) && n.moduleSpecifier && ts.isStringLiteral(n.moduleSpecifier)) {
			imports.push(n.moduleSpecifier.text);
		}
		if (ts.isCallExpression(n)) {
			if (n.expression.kind === ts.SyntaxKind.ImportKeyword && n.arguments[0] && ts.isStringLiteral(n.arguments[0])) {
				imports.push(n.arguments[0].text);
			}
			const callee = ts.isIdentifier(n.expression) ? n.expression.text : '';
			if (!isServerOnly(file) && (callee === 'fetch' || callee === 'goto')) {
				const arg = n.arguments[0];
				const method = callee === 'fetch' ? tsMethod(n.arguments[1]) : 'GET';
				callTarget(c, file, line(n), callee, tsUrl(arg), arg ? arg.getText(sf) : '', method);
			}
		}
		ts.forEachChild(n, visit);
	};
	visit(sf);
	c.imports.set(file, imports);
}

// --- inventory ---------------------------------------------------------------

async function collect(): Promise<Collector> {
	const c = new Collector();
	const files = [...new Bun.Glob('src/**/*.{svelte,ts,js}').scanSync({ cwd: '.' })].sort();
	if (!files.some((f) => f.startsWith('src/routes/'))) throw new CannotRun('src/routes が見つからない（リポジトリのルートで実行する）');
	for (const file of files) {
		if (TEST_FILE.test(file)) continue;
		const text = await Bun.file(file).text();
		if (file.endsWith('.svelte')) {
			extractSvelte(c, file, text);
			if (file.startsWith('src/routes/') && PAGE_FILE.test(basename(file))) {
				c.add({ key: `route:${routePath(file)}`, kind: 'route', source: file, line: 1 });
			}
		} else {
			extractModule(c, file, text);
		}
	}
	return c;
}

function inventoryJson(items: Item[]): string {
	const unique = new Map<string, Item>();
	for (const i of items) if (!unique.has(i.key)) unique.set(i.key, i);
	const rows = [...unique.values()]
		.sort((a, b) => (a.key < b.key ? -1 : 1))
		.map(({ key, kind, source, reason }) => (reason ? { key, kind, source, reason } : { key, kind, source }));
	return JSON.stringify({ generator: 'e2e-inventory-sveltekit', items: rows }, null, '\t') + '\n';
}

async function readJson(path: string): Promise<unknown> {
	let text: string;
	try {
		text = await Bun.file(path).text();
	} catch {
		throw new CannotRun(`${path} を読めない`);
	}
	try {
		return JSON.parse(text);
	} catch (e) {
		throw new CannotRun(`${path} をJSONとして読めない: ${(e as Error).message}`);
	}
}

async function writeOrCheck(command: 'write' | 'check', out: string): Promise<number> {
	const c = await collect();
	const json = inventoryJson(c.items);
	const unresolved = c.items.filter((i) => i.kind === 'unresolved');
	for (const u of unresolved) console.error(`抽出できない: ${u.source}:${u.line} ${u.key}（${u.reason}）`);
	if (command === 'write') {
		await Bun.write(out, json);
		console.log(`${out}: ${JSON.parse(json).items.length}件`);
		return 0;
	}
	const committed = (await readJson(out)) as { items?: { key: string }[] };
	const before = new Set((committed.items ?? []).map((i) => i.key));
	const after = new Map(c.items.map((i) => [i.key, i]));
	const added = [...after.keys()].filter((k) => !before.has(k)).sort();
	const removed = [...before].filter((k) => !after.has(k)).sort();
	if (json === (await Bun.file(out).text())) {
		console.log(`${out}: ソースと一致（${before.size}件）`);
		return 0;
	}
	console.log(`${out} がソースと合わない。write で作り直し、対応表を直す:`);
	for (const k of added) console.log(`  増えた: ${k}（${after.get(k)!.source}:${after.get(k)!.line}）`);
	for (const k of removed) console.log(`  消えた: ${k}`);
	if (!added.length && !removed.length) console.log('  対象は同じで、種類か理由が変わった');
	return 1;
}

// --- select ------------------------------------------------------------------

/** `$lib`, plus the `"imports"` of package.json written as `"#x/*": "./dir/*"`. */
async function importAliases(): Promise<[string, string][]> {
	const aliases: [string, string][] = [['$lib', 'src/lib']];
	const pkg = (await readJson('package.json')) as { imports?: Record<string, unknown> };
	for (const [from, to] of Object.entries(pkg.imports ?? {})) {
		if (from.endsWith('/*') && typeof to === 'string' && to.endsWith('/*')) aliases.push([from.slice(0, -2), normalize(to.slice(0, -2))]);
	}
	return aliases;
}

function resolveImport(from: string, spec: string, files: Set<string>, aliases: [string, string][]): string | null {
	let base: string | undefined;
	if (spec.startsWith('.')) base = normalize(`${dirname(from)}/${spec}`);
	for (const [alias, dir] of aliases) {
		if (spec === alias || spec.startsWith(`${alias}/`)) base = normalize(`${dir}/${spec.slice(alias.length)}`);
	}
	if (base === undefined) return null;
	// TypeScript lets `./x.js` name `./x.ts`.
	const asTs = base.replace(/\.(m?)js$/, '.$1ts');
	for (const candidate of [base, asTs, `${base}.ts`, `${base}.js`, `${base}.svelte`, `${base}/index.ts`, `${base}/index.js`]) {
		if (files.has(candidate)) return candidate;
	}
	return null;
}

function git(args: string[]): string[] {
	const r = Bun.spawnSync(['git', ...args], { stdout: 'pipe', stderr: 'pipe' });
	if (r.exitCode !== 0) throw new CannotRun(`git ${args.join(' ')}: ${new TextDecoder().decode(r.stderr).trim()}`);
	return new TextDecoder().decode(r.stdout).split('\n').filter(Boolean);
}

async function select(base: string, ledger: string, testsDir: string): Promise<number> {
	const changed = new Set([
		...git(['diff', '--name-only', `${base}...HEAD`]),
		...git(['diff', '--name-only', 'HEAD']),
		...git(['ls-files', '--others', '--exclude-standard'])
	]);
	const c = await collect();
	const files = new Set(c.imports.keys());
	const aliases = await importAliases();
	const importers = new Map<string, Set<string>>();
	for (const [file, specs] of c.imports) {
		for (const spec of specs) {
			const target = resolveImport(file, spec, files, aliases);
			if (target) importers.set(target, (importers.get(target) ?? new Set()).add(file));
		}
	}
	const keysBySource = new Map<string, string[]>();
	for (const i of c.items) keysBySource.set(i.source, [...(keysBySource.get(i.source) ?? []), i.key]);

	const data = (await readJson(`${ledger}/scenarios.json`)) as { scenarios?: { id: string; status: string; covers: string[] }[] };
	const scenarios = data.scenarios ?? [];
	const testCases = new Map<string, string[]>();
	for (const f of new Bun.Glob(`${testsDir}/**/*.{ts,js}`).scanSync({ cwd: '.' })) {
		testCases.set(f, [...(await Bun.file(f).text()).matchAll(/@case:([a-z][a-z0-9-]*)/g)].map((m) => m[1]));
	}

	const picked = new Set<string>();
	const unmapped: string[] = [];
	for (const file of [...changed].sort()) {
		if (testCases.has(file)) {
			testCases.get(file)!.forEach((id) => picked.add(id));
			continue;
		}
		// The file itself and everything that imports it, transitively.
		const reach = new Set([file]);
		const queue = [file];
		while (queue.length) for (const up of importers.get(queue.pop()!) ?? []) if (!reach.has(up)) reach.add(up), queue.push(up);
		const keys = new Set([...reach].flatMap((f) => keysBySource.get(f) ?? []));
		const cases = scenarios.filter((s) => s.covers.some((k) => keys.has(k)));
		if (!cases.length) unmapped.push(file);
		cases.forEach((s) => picked.add(s.id));
	}
	const status = new Map(scenarios.map((s) => [s.id, s.status]));
	const runnable = [...picked].filter((id) => status.get(id) !== 'pending').sort();
	const pending = [...picked].filter((id) => status.get(id) === 'pending').sort();
	console.log(`変更: ${changed.size}ファイル（${base}...HEAD と作業ツリー）`);
	console.log(runnable.length ? `ケース: ${runnable.join(', ')}` : 'ケース: なし');
	if (runnable.length) console.log(`--grep: @case:(${runnable.join('|')})(?![a-z0-9-])`);
	if (pending.length) console.log(`未実装のケース（動かせない）: ${pending.join(', ')}`);
	if (unmapped.length) {
		console.log('対応表から引けない変更（利用先を調べ、関係するケースを足して動かす）:');
		for (const f of unmapped) console.log(`  ${f}`);
	}
	return 0;
}

// --- main --------------------------------------------------------------------

function option(args: string[], name: string, fallback?: string): string {
	const i = args.indexOf(name);
	const value = i >= 0 ? args[i + 1] : fallback;
	if (value === undefined) throw new CannotRun(`${name} を指定する`);
	return value;
}

async function main(): Promise<number> {
	const [command, ...args] = Bun.argv.slice(2);
	try {
		if (command === 'write' || command === 'check') return await writeOrCheck(command, option(args, '--out', 'e2e/ledger/inventory.json'));
		if (command === 'select') return await select(option(args, '--base'), option(args, '--ledger', 'e2e/ledger'), option(args, '--tests', 'e2e'));
		throw new CannotRun('使い方: write | check | select --base <ref>');
	} catch (e) {
		if (!(e instanceof CannotRun)) throw e;
		console.error(`実行できない: ${e.message}`);
		return 2;
	}
}

process.exitCode = await main();
