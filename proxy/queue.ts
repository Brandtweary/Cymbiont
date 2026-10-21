export type State = "waiting" | "executing" | "completed" | "interrupted" | "preempted" | "failed";
export class AdmissionError extends Error {
  constructor(public code: string, public status = 503) { super(code); }
}
interface Entry {
  id: string; conversation: string; priority: "foreground" | "background";
  state: State; controller: AbortController; timer?: ReturnType<typeof setTimeout>;
  resolve: (lease: Lease) => void; reject: (error: Error) => void;
  cleanup: () => void; created: number; ended?: number;
}
export interface Lease { signal: AbortSignal; finish: (state?: "completed" | "failed") => void }
/** One completion owns the inference resource through response-body consumption. */
export class CompletionQueue {
  private entries = new Map<string, Entry>();
  private waiting: Entry[] = [];
  private active?: Entry;
  private last = { foreground: "", background: "" };
  constructor(private limits: {queueCapacity: number; queueTimeoutMs: number; executionTimeoutMs: number},
    private record: (event: object) => void = () => {}) {}
  status(id: string) {
    this.prune();
    const entry = this.entries.get(id);
    return entry ? {id, state: entry.state, position: entry.state === "waiting" ? this.waiting.indexOf(entry) + 1 : 0} : null;
  }
  private prune() {
    for (const [id, e] of this.entries) if (e.ended && Date.now() - e.ended > 60_000) this.entries.delete(id);
    const ended = [...this.entries.values()].filter(e => e.ended);
    for (const e of ended.slice(0, Math.max(0, ended.length - this.limits.queueCapacity * 2))) this.entries.delete(e.id);
  }
  acquire(id: string, conversation: string, priority: "foreground" | "background", signal: AbortSignal): Promise<Lease> {
    this.prune();
    if (signal.aborted) return Promise.reject(new AdmissionError("interrupted", 499));
    if (this.entries.has(id)) return Promise.reject(new AdmissionError("duplicate_request", 409));
    if (this.active && this.waiting.length >= this.limits.queueCapacity) return Promise.reject(new AdmissionError("queue_full", 429));
    return new Promise((resolve, reject) => {
      const abort = () => this.cancel(id);
      const entry: Entry = {id, conversation, priority, state: "waiting", controller: new AbortController(), resolve, reject,
        cleanup: () => signal.removeEventListener("abort", abort), created: Date.now()};
      signal.addEventListener("abort", abort, {once: true});
      this.entries.set(id, entry); this.waiting.push(entry);
      entry.timer = setTimeout(() => this.stop(entry, "queue_timeout"), this.limits.queueTimeoutMs);
      this.record({id, state: "waiting"}); this.advance();
      // A foreground chat preempts an executing background round: one inference
      // resource, and a visitor's message must not queue behind multi-second
      // background generation. The aborted entry releases its slot only when its
      // upstream request actually unwinds, so the foreground admission that
      // follows sees a free resource, never a half-aborted one.
      if (priority === "foreground" && this.active?.priority === "background") this.stop(this.active, "preempted");
    });
  }
  cancel(id: string) { const entry = this.entries.get(id); if (!entry || entry.ended) return false; this.stop(entry, "interrupted"); return true; }
  private stop(entry: Entry, code: string) {
    if (entry.ended) return;
    const status = code === "interrupted" ? 499 : code === "preempted" ? 503 : 504;
    entry.controller.abort(new AdmissionError(code, status));
    if (entry.state === "waiting") {
      entry.reject(new AdmissionError(code, status));
      this.finish(entry, code === "interrupted" ? "interrupted" : code === "preempted" ? "preempted" : "failed");
    }
    // Executing callers release only after the upstream request actually unwinds.
  }
  private finish(entry: Entry, state: State) {
    if (entry.ended) return;
    clearTimeout(entry.timer); entry.cleanup(); entry.state = state; entry.ended = Date.now();
    this.waiting = this.waiting.filter(e => e !== entry);
    if (this.active === entry) this.active = undefined;
    this.record({id: entry.id, state, elapsedMs: entry.ended - entry.created}); this.advance();
  }
  private advance() {
    if (this.active || !this.waiting.length) return;
    const priority = this.waiting.some(e => e.priority === "foreground") ? "foreground" : "background";
    const pool = this.waiting.filter(e => e.priority === priority);
    const entry = pool.find(e => e.conversation !== this.last[priority]) ?? pool[0]!;
    this.waiting = [...this.waiting.filter(e => e !== entry && e.conversation !== entry.conversation), ...this.waiting.filter(e => e !== entry && e.conversation === entry.conversation)]; this.active = entry; this.last[priority] = entry.conversation;
    clearTimeout(entry.timer); entry.state = "executing";
    entry.timer = setTimeout(() => this.stop(entry, "execution_timeout"), this.limits.executionTimeoutMs);
    this.record({id: entry.id, state: "executing", waitedMs: Date.now() - entry.created});
    entry.resolve({signal: entry.controller.signal, finish: (state = "completed") => this.finish(entry,
      entry.controller.signal.aborted ? (entry.controller.signal.reason?.code === "interrupted" ? "interrupted" : entry.controller.signal.reason?.code === "preempted" ? "preempted" : "failed") : state)});
  }
}
