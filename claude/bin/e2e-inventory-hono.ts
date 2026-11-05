#!/usr/bin/env node
/**
 * List the API coverage targets of a Hono app.
 *
 *   node .claude/bin/e2e-inventory-hono.ts write --app src/app.ts [--export app] [--out e2e/ledger/inventory.json]
 *   node .claude/bin/e2e-inventory-hono.ts check --app src/app.ts [--export app] [--out e2e/ledger/inventory.json]
 *
 * Run it from the repository root. It imports the app module and reads its routes with
 * `inspectRoutes` from the project's own `hono/dev`, so the module must not connect to a database
 * or start a server when imported. If Node.js cannot load the app's TypeScript (imports without
 * extensions, path aliases), run it as `node --import tsx .claude/bin/e2e-inventory-hono.ts ...`.
 * The ledger format is defined in .claude/references/verification-map.md.
 * Exit codes: 0 ok, 1 inventory out of date, 2 could not run.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

type Item = { key: string; kind: 'api'; source: string };
type Route = { method: string; path: string; isMiddleware: boolean };

class CannotRun extends Error {}

const dirname = (p: string) => p.slice(0, Math.max(p.lastIndexOf('/'), 0));

async function collect(appPath: string, exportName: string): Promise<Item[]> {
	let mod: Record<string, unknown>;
	try {
		mod = await import(pathToFileURL(resolve(appPath)).href);
	} catch (e) {
		throw new CannotRun(`${appPath} をimportできない: ${(e as Error).message}（TypeScriptを読めないなら node --import tsx で動かす）`);
	}
	const app = mod[exportName] as { routes?: unknown } | undefined;
	if (!app || !Array.isArray(app.routes)) throw new CannotRun(`${appPath} の ${exportName} がHonoのアプリではない（--export で名前を指定する）`);
	// The project's own hono, resolved from the app, so the route list matches the app's version.
	let inspectRoutes: (app: unknown) => Route[];
	try {
		const dev = createRequire(resolve(appPath)).resolve('hono/dev');
		({ inspectRoutes } = await import(pathToFileURL(dev).href));
	} catch (e) {
		throw new CannotRun(`hono/dev を読めない: ${(e as Error).message}`);
	}
	return inspectRoutes(app)
		.filter((r) => !r.isMiddleware)
		.map((r) => ({ key: `api:${r.method} ${r.path}`, kind: 'api', source: appPath }));
}

function inventoryJson(items: Item[]): string {
	const unique = new Map<string, Item>();
	for (const i of items) if (!unique.has(i.key)) unique.set(i.key, i);
	const rows = [...unique.values()].sort((a, b) => (a.key < b.key ? -1 : 1));
	return JSON.stringify({ generator: 'e2e-inventory-hono', items: rows }, null, '\t') + '\n';
}

function readText(path: string): string {
	try {
		return readFileSync(path, 'utf8');
	} catch {
		throw new CannotRun(`${path} を読めない`);
	}
}

async function writeOrCheck(command: 'write' | 'check', appPath: string, exportName: string, out: string): Promise<number> {
	const json = inventoryJson(await collect(appPath, exportName));
	const count = (JSON.parse(json) as { items: Item[] }).items.length;
	if (command === 'write') {
		if (dirname(out)) mkdirSync(dirname(out), { recursive: true });
		writeFileSync(out, json);
		console.log(`${out}: ${count}件`);
		return 0;
	}
	const text = readText(out);
	if (json === text) {
		console.log(`${out}: ソースと一致（${count}件）`);
		return 0;
	}
	let committed: { items?: { key: string }[] };
	try {
		committed = JSON.parse(text);
	} catch (e) {
		throw new CannotRun(`${out} をJSONとして読めない: ${(e as Error).message}`);
	}
	const before = new Set((committed.items ?? []).map((i) => i.key));
	const after = new Set((JSON.parse(json) as { items: Item[] }).items.map((i) => i.key));
	console.log(`${out} がソースと合わない。write で作り直し、対応表を直す:`);
	for (const k of [...after].filter((k) => !before.has(k)).sort()) console.log(`  増えた: ${k}`);
	for (const k of [...before].filter((k) => !after.has(k)).sort()) console.log(`  消えた: ${k}`);
	return 1;
}

function option(args: string[], name: string, fallback?: string): string {
	const i = args.indexOf(name);
	const value = i >= 0 ? args[i + 1] : fallback;
	if (value === undefined) throw new CannotRun(`${name} を指定する`);
	return value;
}

async function main(): Promise<number> {
	const [command, ...args] = process.argv.slice(2);
	try {
		if (command === 'write' || command === 'check') {
			return await writeOrCheck(command, option(args, '--app'), option(args, '--export', 'default'), option(args, '--out', 'e2e/ledger/inventory.json'));
		}
		throw new CannotRun('使い方: write | check --app <file> [--export <name>] [--out <file>]');
	} catch (e) {
		if (!(e instanceof CannotRun)) throw e;
		console.error(`実行できない: ${e.message}`);
		return 2;
	}
}

// An app that keeps handles open on import (timers, pools) must not keep the extractor running.
// No top-level await: tsx compiles this file as CommonJS in a project without "type": "module".
main().then((code) => process.exit(code));
