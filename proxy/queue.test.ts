import {test, expect} from "bun:test";
import {CompletionQueue} from "./queue";
const signal = () => new AbortController().signal;
const limits = {queueCapacity: 8, queueTimeoutMs: 1000, executionTimeoutMs: 1000};
test("one active completion, foreground priority and conversation rotation", async () => {
 const q = new CompletionQueue(limits);
 const first = await q.acquire("first", "A", "foreground", signal());
 const pending = [q.acquire("a1", "A", "foreground", signal()), q.acquire("b1", "B", "foreground", signal()), q.acquire("a2", "A", "foreground", signal()), q.acquire("c1", "C", "foreground", signal())];
 const bg = q.acquire("bg", "D", "background", signal());
 first.finish(); expect(q.status("b1")?.state).toBe("executing");
 (await pending[1]!).finish(); expect(q.status("a1")?.state).toBe("executing");
 (await pending[0]!).finish(); expect(q.status("c1")?.state).toBe("executing");
 (await pending[3]!).finish(); (await pending[2]!).finish(); (await bg).finish();
});
test("queued cancellation never consumes resource and queue is bounded", async () => {
 const q = new CompletionQueue({...limits, queueCapacity: 1}); const active = await q.acquire("one", "A", "foreground", signal());
 const pending = q.acquire("two", "B", "foreground", signal());
 await expect(q.acquire("three", "C", "foreground", signal())).rejects.toThrow("queue_full");
 q.cancel("two"); await expect(pending).rejects.toThrow("interrupted"); active.finish();
 expect(q.status("two")?.state).toBe("interrupted");
});
test("execution timeout starts after admission and holds slot until upstream unwinds", async () => {
 const q = new CompletionQueue({...limits, executionTimeoutMs: 20}); const a = await q.acquire("a", "A", "foreground", signal());
 const b = q.acquire("b", "B", "foreground", signal());
 await new Promise(resolve => setTimeout(resolve, 30)); expect(a.signal.aborted).toBe(true); expect(q.status("b")?.state).toBe("waiting");
 a.finish(); const next = await b; expect(next.signal.aborted).toBe(false); next.finish();
});
test("a foreground arrival preempts the executing background round, not other waiting work", async () => {
 const q = new CompletionQueue(limits);
 const bg = await q.acquire("bg", "D", "background", signal());
 let bgAborted = ""; bg.signal.addEventListener("abort", () => { bgAborted = (bg.signal.reason as {code: string}).code; });
 const fg = q.acquire("fg", "E", "foreground", signal());
 expect(bgAborted).toBe("preempted"); // preemption is immediate, not at the next round boundary
 expect(q.status("fg")?.state).toBe("waiting"); // the slot is held until the background upstream unwinds
 bg.finish(); // executing caller releases after the aborted request actually unwinds
 const lease = await fg; expect(lease.signal.aborted).toBe(false); lease.finish();
 expect(q.status("bg")?.state).toBe("preempted");
});
test("foreground arrivals do not preempt an executing foreground round", async () => {
 const q = new CompletionQueue(limits);
 const first = await q.acquire("one", "A", "foreground", signal());
 const second = q.acquire("two", "B", "foreground", signal());
 expect(first.signal.aborted).toBe(false); expect(q.status("two")?.state).toBe("waiting");
 first.finish(); (await second).finish();
});
