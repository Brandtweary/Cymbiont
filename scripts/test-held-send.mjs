// Regression: a send that lands while the session is streaming must be held and
// fire when the run ends, not vanish. Before the fix, Enter during a run was
// ignored by MessageEditor and silently returned by AgentInterface.sendMessage —
// no request, no feedback; the visitor's message existed only as the leftover
// composer draft. Run: node scripts/test-held-send.mjs (see test-composer-lifecycle.mjs).
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
const root=fileURLToPath(new URL('../',import.meta.url));
const executablePath=process.env.BROWSER_EXECUTABLE || execFileSync('which',['brave'],{encoding:'utf8'}).trim();
// The fixture session exposes prompt() and the raw lifecycle events the
// interface subscribes to. prompt() resolves on demand so a "run" can be held
// open while a second send arrives — exactly the live bug's shape.
const bundle=await build({stdin:{contents:`
import {ChatPanel} from './src/pi-web-ui/ChatPanel.ts';
import {setAppStorage} from './src/pi-web-ui/storage/app-storage.ts';
setAppStorage({providerKeys:{get:async()=> 'local'}});
const makeSession=()=>{return{state:{model:{id:'fixture',provider:'fixture',reasoning:false},messages:[],tools:[],isStreaming:false,pendingToolCalls:new Set(),thinkingLevel:'off'},subscribe:(fn)=>{window.listeners.push(fn);return()=>{};},streamFn:()=>{},getApiKey:()=>'local',
prompt:message=>new Promise(resolve=>{window.sent.push(message);window.resolveSend=resolve;})};};
window.sent=[];window.listeners=[];
window.setup=async()=>{const panel=new ChatPanel();document.body.append(panel);await panel.setAgent(makeSession());await panel.updateComplete;await panel.agentInterface.updateComplete;await panel.querySelector('message-editor').updateComplete;window.session=panel.agentInterface.session;};
window.emit=(event)=>{for(const fn of [...window.listeners])fn(event);};
`,resolveDir:root,loader:'ts'},bundle:true,format:'iife',platform:'browser',define:{'import.meta.env':'{}','import.meta.url':'"https://fixture.invalid/"'},write:false,logLevel:'silent'});
const browser=await chromium.launch({executablePath,headless:true});
try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));
 await page.goto('https://fixture.invalid/');
 await page.addScriptTag({content:bundle.outputFiles[0].text});await page.evaluate(()=>window.setup());
 const endRun=()=>page.evaluate(async()=>{window.session.state.isStreaming=false;window.emit({type:'agent_end',messages:[]});await new Promise(r=>setTimeout(r,50));});
 // The real agent emits message_start when the model begins; the admission
 // hook that clears the composer draft listens for it.
 const deliver=()=>page.evaluate(()=>{for(const message of window.sent)window.emit({type:'message_start',message});});
 // 1. A send during a run is held, not dropped: no prompt yet, draft retained,
 //    and the hold is visible.
 await page.evaluate(()=>{window.session.state.isStreaming=true;});
 await page.locator('message-editor textarea').fill('held while replying');
 await page.locator('message-editor textarea').press('Enter');
 assert.equal(await page.evaluate(()=>window.sent.length),0,'a held send fires no prompt');
 assert.equal(await page.locator('message-editor textarea').inputValue(),'held while replying','the draft stays visible while held');
 assert.match(await page.getByRole('status').innerText(),/will send when it finishes/,'the hold is announced');
 // 2. When the run ends the held send fires and clears the draft once admitted.
 await endRun();
 assert.equal(await page.evaluate(()=>window.sent.length),1,'the held send fires after the run');
 assert.equal(await page.evaluate(()=>window.sent[0].content),'held while replying');
 await deliver();
 assert.equal(await page.locator('message-editor textarea').inputValue(),'','the admitted send clears the draft');
 await page.evaluate(()=>{window.resolveSend();});
 // 3. A newer send replaces the held one — the visitor's latest text wins.
 await page.evaluate(()=>{window.session.state.isStreaming=true;});
 await page.locator('message-editor textarea').fill('superseded');
 await page.locator('message-editor textarea').press('Enter');
 await page.locator('message-editor textarea').fill('latest intent');
 await page.locator('message-editor textarea').press('Enter');
 await endRun();
 assert.equal(await page.evaluate(()=>window.sent.length),2,'only the replacement sends');
 assert.equal(await page.evaluate(()=>window.sent[1].content),'latest intent','the newest send replaces the hold');
 await deliver();
 await page.evaluate(()=>{window.resolveSend();});
 // 4. A send that lands while another send is still inside prompt() — the
 //    preparation window — is held too, and fires from that send's completion.
 await page.locator('message-editor textarea').fill('first send');
 await page.locator('message-editor textarea').press('Enter');
 assert.equal(await page.evaluate(()=>window.sent.length),3,'the first send went through');
 await page.evaluate(()=>{window.session.state.isStreaming=true;}); // its run started
 await page.locator('message-editor textarea').fill('held during preparation');
 await page.locator('message-editor textarea').press('Enter');
 // agent_end alone does not flush: the first send still owns the session.
 await endRun();
 assert.equal(await page.evaluate(()=>window.sent.length),3,'a send held mid-preparation does not jump the owner');
 await page.evaluate(()=>{window.resolveSend();});
 await page.waitForTimeout(50);
 assert.equal(await page.evaluate(()=>window.sent.length),4,'the held send fires when the other send completes');
 assert.equal(await page.evaluate(()=>window.sent[3].content),'held during preparation');
 assert.deepEqual(errors,[],'held sends do not leak unhandled errors');
 console.log('Held-send regression passed: held during runs, fired on idle, newest wins, preparation window covered');
}finally{await browser.close();}
