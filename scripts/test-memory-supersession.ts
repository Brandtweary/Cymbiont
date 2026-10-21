import assert from "node:assert/strict";
import { test } from "node:test";
import { IDBFactory, IDBKeyRange } from "fake-indexeddb";
import { PipelineRuntime, type PipelineDeps } from "../src/pipeline.js";
import { MemoryStorage } from "../src/memory-storage.js";
import { IndexedDBStorageBackend } from "../src/pi-web-ui/storage/backends/indexeddb-storage-backend.js";
import { Graph } from "../src/kg/graph.js";
import type { GraphAsset } from "../src/kg/types.js";
import type { ConversationArchive } from "../src/conversation-history.js";

// Regression: memory sweeps are single-flight per conversation. At most one
// tick for a conversation is running or pending, ever. A turn completing while
// a tick is outstanding supersedes it — cancelled, never re-run — and the
// superseding sweep anchors its coverage to the last COMPLETED boundary so it
// sees every uncovered turn, never just the latest exchange. Removal and
// admission publish atomically, so a reload never resurrects a superseded tick.
// Run: tsx scripts/test-memory-supersession.ts

globalThis.indexedDB = new IDBFactory();
globalThis.IDBKeyRange = IDBKeyRange;
const completed = () => [{ role: "assistant", content: [{ type: "text", text: "Complete" }], stopReason: "stop", usage: { input: 1, output: 1 } }] as any;
const preempted = () => [{ role: "assistant", content: [{ type: "text", text: "" }], stopReason: "error", errorMessage: '{"code":"preempted"}', usage: { input: 1, output: 1 } }] as any;
const record = (id: string, text: string) => ({ id, message: { role: "user", content: text, timestamp: 1 } as any });
const deferred = () => { let resolve!: () => void; const promise = new Promise<void>(r => { resolve = r; }); return { promise, resolve }; };
const isAudit = (context: any) => !!context.tools.find((t: any) => t.name === "audit_handoff");
let serial = 0;
function backend(name = `supersession-${serial++}`) {
  return new IndexedDBStorageBackend({ dbName: name, version: 1,
    stores: ["lexicon", "pipeline", "memory-consent"].map(store => ({ name: store })) });
}
async function fixture(options: { raw?: ReturnType<typeof backend>; loop?: PipelineDeps["runLoop"]; foregroundActive?: () => boolean } = {}) {
  const raw = options.raw ?? backend(); const storage = new MemoryStorage(raw);
  const saved = await storage.load(); let graph = saved.graph.present ? new Graph(saved.graph.value as GraphAsset) : Graph.empty();
  const histories = new Map<string, { revision: number; archive: ConversationArchive }>();
  let consent = "granted"; const errors: unknown[] = []; const prompts: string[] = [];
  const runtime = new PipelineRuntime({ backend: raw, getGraph: () => graph, setGraph: next => { graph = next; },
    publishMemory: async (asset, state, archive, guard) => { await storage.save({ graph: asset, pipeline: state, ...(archive ? { archive } : {}) }, guard); },
    getRawHistory: async key => structuredClone(histories.get(key) ?? null),
    measureContext: async () => 1, getRoleInputBudget: () => 1000000, getRoleOutputBudget: () => 1000000,
    embed: async () => null, getModel: () => ({} as any), getBaseUrl: () => "invalid", getModelId: () => "fixture", getAuth: () => "not-persisted",
    getConsent: () => storage.invalidated ? "declined" : consent, addCost: () => {}, onStateChange: () => {}, onActivity: () => {},
    onError: error => { errors.push(error); }, foregroundActive: options.foregroundActive,
    runLoop: async (...args) => {
      prompts.push(String((args[0][0] as any).content));
      const output = await (options.loop ?? (async () => completed()))(...args);
      const summaryDraft = args[1].tools!.find(tool => tool.name === "summary_draft");
      if (summaryDraft) await summaryDraft.execute("finish", { operation: "store", text: "The user maintains an orchard." }, undefined, undefined);
      else await args[1].tools!.find(tool => tool.name === "memory_finish")!.execute("finish", { outcome: "completed", reason: "Fixture completed" }, undefined, undefined);
      return output;
    }, completion: args => async () => { args.onUsage?.({ promptTokens: 1, completionTokens: 1 }); return "The user maintains an orchard."; },
  });
  runtime.loadSnapshot(saved); runtime.startSession("conversation");
  const enqueue = async (records: Array<{ id: string; message: any }>) => {
    const revision = (histories.get("conversation")?.revision ?? 0) + 1;
    const archive = { version: 1, complete: true, records } as ConversationArchive;
    histories.set("conversation", { revision, archive });
    await runtime.onTurnEndHistory({ sessionKey: "conversation", revision, archive }, false);
  };
  return { runtime, storage, raw, prompts, errors, graph: () => graph, enqueue };
}
async function until(predicate: () => boolean, timeoutMs = 5000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("condition not reached within timeout");
    await new Promise(resolve => setTimeout(resolve, 25));
  }
}
// The activity feed line a parked stage pushes once its park is durable —
// the synchronization point for "the preemption round really landed".
const parked = (runtime: PipelineRuntime) => runtime.activity.some(a => a.agent === "audit" && a.line.includes("paused"));
const summaries = (runtime: PipelineRuntime) => runtime.activity.filter(a => a.agent === "summary" && a.line.includes("updated conversation summary")).length;

test("rapid successive turns produce exactly one sweep whose evidence windows cover both turns", async () => {
  const entered = deferred(), release = deferred();
  const h = await fixture({ loop: async () => { entered.resolve(); await release.promise; return completed(); } });
  await h.enqueue([record("raw-one", "Remember orchard tools")]);
  await entered.promise;
  // The second turn completes while the first sweep's audit is still in flight.
  await h.enqueue([record("raw-one", "Remember orchard tools"), record("raw-two", "and the greenhouse")]);
  release.resolve();
  await h.runtime.whenIdle();
  const jobs = h.runtime.snapshot().jobs!;
  assert.equal(jobs.length, 1); // the in-flight sweep was superseded, not stacked beneath
  assert.equal(jobs[0].coverageStart, 0); // no completed boundary yet: the whole conversation
  assert.equal(jobs[0].history!.count, 2);
  assert.deepEqual(jobs[0].stages, { audit: "complete", memory: "complete", summary: "complete" });
  // Requirement: the surviving sweep's windows carry ALL uncovered turns.
  const covering = h.prompts.filter(p => p.includes("and the greenhouse"));
  assert.equal(covering.length, 2); // audit and memory of the surviving sweep only
  assert(covering.every(p => p.includes("Remember orchard tools"))); // turn one was not truncated away
  assert.equal(summaries(h.runtime), 1); // one summary publication, not one per turn
  assert.equal(h.errors.length, 0);
});

test("a parked tick is superseded by the interrupting turn and never re-runs", async () => {
  let auditCalls = 0; let chatBusy = true;
  const h = await fixture({ foregroundActive: () => chatBusy, loop: async (_messages, context) => {
    if (isAudit(context) && auditCalls++ === 0) return preempted(); // the foreground chat preempts the round
    return completed();
  } });
  await h.enqueue([record("raw-one", "Remember orchard tools")]);
  await until(() => parked(h.runtime)); // the round is parked, durably pending
  // The visitor's chat finishes: its tick supersedes the parked one.
  chatBusy = false;
  await h.enqueue([record("raw-one", "Remember orchard tools"), record("raw-two", "and the greenhouse")]);
  await h.runtime.whenIdle();
  // The parked round re-ran zero times: audit was attempted exactly twice —
  // the preempted round and the surviving sweep's own audit.
  assert.equal(auditCalls, 2);
  const jobs = h.runtime.snapshot().jobs!;
  assert.equal(jobs.length, 1);
  assert.deepEqual(jobs[0].stages, { audit: "complete", memory: "complete", summary: "complete" });
  assert.equal(summaries(h.runtime), 1); // exactly one summary publication
  assert.equal(h.errors.length, 0);
  // Durable receipts: three cancelled records, and no half-state left behind.
  const cancelled = (await h.storage.readArchive()).records.filter(row => row.status === "cancelled");
  assert.equal(cancelled.length, 3);
  assert(cancelled.every(row => (row.payload as any).outcome.reason === "Superseded by a newer turn"));
  // A reload never resurrects the superseded tick.
  let replayed = 0;
  const reloaded = await fixture({ raw: h.raw, loop: async () => { replayed++; return completed(); } });
  reloaded.runtime.resumePending();
  await reloaded.runtime.whenIdle();
  assert.equal(replayed, 0);
  assert.equal(reloaded.runtime.hasFailedWork, false);
});

test("the superseding sweep anchors coverage to the last completed boundary, not the superseded tick's start", async () => {
  let audits = 0; let chatBusy = false;
  const h = await fixture({ foregroundActive: () => chatBusy, loop: async (_messages, context) => {
    if (isAudit(context) && ++audits === 2) { chatBusy = true; return preempted(); } // the second sweep is preempted mid-audit
    return completed();
  } });
  // First sweep completes: coverage boundary is two records.
  await h.enqueue([record("raw-one", "first turn"), record("raw-two", "second turn")]);
  await h.runtime.whenIdle();
  assert.equal(summaries(h.runtime), 1);
  // The second sweep (three records) is admitted, then preempted and parked.
  await h.enqueue([record("raw-one", "first turn"), record("raw-two", "second turn"), record("raw-three", "third turn")]);
  await until(() => parked(h.runtime));
  // The interrupting chat finishes: its turn supersedes the parked sweep with a fourth record.
  chatBusy = false;
  await h.enqueue([record("raw-one", "first turn"), record("raw-two", "second turn"), record("raw-three", "third turn"), record("raw-four", "fourth turn")]);
  await h.runtime.whenIdle();
  const jobs = h.runtime.snapshot().jobs!;
  assert.equal(jobs.length, 2); // the completed first sweep plus the surviving sweep
  const survivor = jobs[1];
  assert.equal(survivor.coverageStart, 2); // the last completed boundary, NOT the superseded tick's 3-record start
  assert.equal(survivor.history!.count, 4);
  // No-skip invariant: both uncovered turns reached the surviving sweep's windows.
  const covering = h.prompts.filter(p => p.includes("fourth turn"));
  assert.equal(covering.length, 2); // audit and memory of the surviving sweep only
  assert(covering.every(p => p.includes("third turn")));
  assert(covering.every(p => !p.includes("first turn"))); // acknowledged turns stay behind the boundary
  assert.equal(summaries(h.runtime), 2); // one publication per completed sweep, none for the superseded
  assert.equal(h.errors.length, 0);
  // Coverage acks exactly what was processed: the fully covered conversation admits no new sweep.
  await h.enqueue([record("raw-one", "first turn"), record("raw-two", "second turn"), record("raw-three", "third turn"), record("raw-four", "fourth turn")]);
  await h.runtime.whenIdle();
  assert.equal(h.runtime.snapshot().jobs!.length, 2);
});
