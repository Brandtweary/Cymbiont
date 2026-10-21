import assert from 'node:assert/strict';
import { IDBFactory, IDBKeyRange } from 'fake-indexeddb';
import { createServer } from 'vite';

// Regression: the audit agent once skipped the phonetic_candidates tool and
// cleared a garbled voice turn on "rawText and correctedText identical" — which
// only proves no auto-replacement had already fired, never that the
// transcription was accurate. The pipeline now computes the acoustic candidate
// report itself and presents it as standing evidence in the audit prompt, so
// flagged candidates reach the audit regardless of any model choice. A missing
// or failing pronunciation service fails open to a stated unavailability
// section, never to model discretion. Run: tsx scripts/test-audit-phonetic-evidence.ts

globalThis.indexedDB = new IDBFactory();
globalThis.IDBKeyRange = IDBKeyRange;

const server = await createServer({ optimizeDeps: { noDiscovery: true, include: [] }, server: { middlewareMode: true, hmr: false }, appType: 'custom' });
try {
	const { PipelineRuntime } = await server.ssrLoadModule('/src/pipeline.ts');
	const { MemoryStorage } = await server.ssrLoadModule('/src/memory-storage.ts');
	const { IndexedDBStorageBackend } = await server.ssrLoadModule('/src/pi-web-ui/storage/backends/indexeddb-storage-backend.ts');
	const { Graph } = await server.ssrLoadModule('/src/kg/graph.ts');

	// The model makes NO tool calls in these fixtures: whatever reaches the audit
	// prompt arrived there mechanically. Every pronunciation collapses to one
	// syllable, so any flagged span proves the presented report, not the stub's
	// judgement of sound.
	const phonemize = async (texts: string[]) => ({ phonemes: texts.map(() => 'kə'), engine: { name: 'espeak-ng', version: 'fixture', voice: 'en-us' as const } });
	const completed = () => [{ role: 'assistant', content: [{ type: 'text', text: 'Complete' }], stopReason: 'stop', usage: { input: 1, output: 1 } }] as any;
	const isAudit = (context: any) => !!context.tools.find((t: any) => t.name === 'audit_handoff');
	const SECTION = 'Pre-computed acoustic candidates';
	let serial = 0;
	function backend() {
		return new IndexedDBStorageBackend({ dbName: `phonetic-evidence-${serial++}`, version: 1,
			stores: ['lexicon', 'pipeline', 'memory-consent'].map(name => ({ name })) });
	}
	async function fixture(options: { phonemize?: (texts: string[], signal?: AbortSignal) => Promise<{ phonemes: string[]; engine: unknown }>; seed?: boolean } = {}) {
		const raw = backend(); const storage = new MemoryStorage(raw);
		if (options.seed) { await storage.load(); const graph = Graph.empty(); graph.getOrCreate('kubernetes', 'A container orchestration platform.'); await storage.save({ graph: graph.serialize() }); }
		const saved = await storage.load(); let graph = saved.graph.present ? new (Graph as any)(saved.graph.value) : (Graph as any).empty();
		const errors: unknown[] = []; const prompts: string[] = [];
		const runtime = new PipelineRuntime({ backend: raw, getGraph: () => graph, setGraph: next => { graph = next; },
			publishMemory: async (asset, state, archive, guard) => { await storage.save({ graph: asset, pipeline: state, ...(archive ? { archive } : {}) }, guard); },
			measureContext: async () => 1, getRoleInputBudget: () => 1000000, getRoleOutputBudget: () => 1000000,
			embed: async () => null, phonemize: options.phonemize, getModel: () => ({} as any), getBaseUrl: () => 'invalid', getModelId: () => 'fixture', getAuth: () => 'not-persisted',
			getConsent: () => storage.invalidated ? 'declined' : 'granted', addCost: () => {}, onStateChange: () => {}, onActivity: () => {},
			onError: error => { errors.push(error); },
			runLoop: async (...args: any[]) => {
				prompts.push(String(args[0][0].content));
				const output = await completed();
				const summaryDraft = args[1].tools!.find((tool: any) => tool.name === 'summary_draft');
				if (summaryDraft) await summaryDraft.execute('finish', { operation: 'store', text: 'The user deploys clusters.' }, undefined, undefined);
				else await args[1].tools!.find((tool: any) => tool.name === 'memory_finish')!.execute('finish', { outcome: 'completed', reason: 'Fixture completed' }, undefined, undefined);
				return output;
			}, completion: (args: any) => async () => { args.onUsage?.({ promptTokens: 1, completionTokens: 1 }); return '[NO_ENTRY]'; },
		});
		runtime.loadSnapshot(saved); runtime.startSession('conversation');
		return { runtime, prompts, errors };
	}

	// A real garble with no prior correction: rawText == correctedText == the garble.
	const voiceMessages = [{ role: 'user', content: 'kuber netties on the cluster', timestamp: 1 }] as any;
	const voiceEvidence = { utteranceId: 'u1', rawText: 'kuber netties', correctedText: 'kuber netties' };

	{
		const h = await fixture({ phonemize, seed: true });
		h.runtime.onTurnEnd(() => voiceMessages, true, voiceEvidence);
		await h.runtime.whenIdle();
		const audits = h.prompts.filter(p => p.includes('## Your role: audit'));
		assert.equal(audits.length, 1);
		// The candidate report is standing evidence in the audit prompt even though
		// the model made zero tool calls, and even though rawText == correctedText.
		assert(audits[0].includes(SECTION));
		assert(audits[0].includes('"heard":"kuber netties"'));
		assert(audits[0].includes('"proposed":"kubernetes"'));
		// The section is audit-only: memory and summary prompts never carry it.
		for (const prompt of h.prompts) if (!prompt.includes('## Your role: audit')) assert(!prompt.includes(SECTION));
		assert.deepEqual(h.runtime.snapshot().jobs![0].stages, { audit: 'complete', memory: 'complete', summary: 'complete' });
		assert.equal(h.errors.length, 0);
	}

	{
		// A typed turn presents no candidate section — nothing was spoken.
		const h = await fixture({ phonemize, seed: true });
		h.runtime.onTurnEnd(() => [{ role: 'user', content: 'typed words', timestamp: 1 }] as any, false, undefined);
		await h.runtime.whenIdle();
		const audits = h.prompts.filter(p => p.includes('## Your role: audit'));
		assert.equal(audits.length, 1);
		assert(!audits[0].includes(SECTION));
		assert.equal(h.errors.length, 0);
	}

	{
		// No pronunciation service configured: fail open to a stated section.
		const h = await fixture({ seed: true });
		h.runtime.onTurnEnd(() => voiceMessages, true, voiceEvidence);
		await h.runtime.whenIdle();
		const audits = h.prompts.filter(p => p.includes('## Your role: audit'));
		assert.equal(audits.length, 1);
		assert(audits[0].includes(SECTION));
		assert(audits[0].includes('unavailable'));
		assert.equal(h.errors.length, 0);
	}

	{
		// A failing pronunciation service also fails open; the stage still completes.
		const h = await fixture({ phonemize: async () => { throw new Error('service down'); }, seed: true });
		h.runtime.onTurnEnd(() => voiceMessages, true, voiceEvidence);
		await h.runtime.whenIdle();
		const audits = h.prompts.filter(p => p.includes('## Your role: audit'));
		assert.equal(audits.length, 1);
		assert(audits[0].includes(SECTION));
		assert(audits[0].includes('unavailable'));
		assert.deepEqual(h.runtime.snapshot().jobs![0].stages, { audit: 'complete', memory: 'complete', summary: 'complete' });
		assert.equal(h.errors.length, 0);
	}

	console.log('Audit standing phonetic evidence regressions passed');
} finally { await server.close(); }
