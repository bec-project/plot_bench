"""Exercise the shared HTML form's actual script without a browser dependency."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_source_controls_preserve_concurrent_changes_and_preset_drafts():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed to execute the source controls JavaScript")
    html = (Path(__file__).parents[1] / "src/plotbench/controls.html").read_text()
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
let server = {hz:30, view:'both', points:10000, append_count:1000, waveform_mode:'replace',
  image_mode:'scalar', width:512, height:512, seed:42, generation:1};
const elements = Object.entries(server).filter(([key]) => key !== 'generation').map(([name,value]) =>
  ({name, value:'', type:typeof value === 'number' ? 'number' : 'select-one'}));
elements.namedItem = name => elements.find(el=>el.name===name);
const preset = id => {
  const markup = SOURCE_HTML.match(new RegExp(`<select id="${id}"[^>]*>([\\s\\S]*?)</select>`))[1];
  return {name:'', value:'', listeners:{},
    options:[...markup.matchAll(/<option value="([^"]*)"/g)].map(match=>({value:match[1]})),
    addEventListener(name, callback) {this.listeners[name]=callback;}};
};
const ratePreset = preset('rate-preset'), resolutionPreset = preset('resolution-preset');
elements.push(ratePreset, resolutionPreset);
const listeners = {}, button = {}, error = {}, status = {}, backend = {};
const form = {elements, querySelector:()=>button, addEventListener:(name,callback)=>listeners[name]=callback};
const document = {activeElement:null, querySelector:selector=>
  ({form, '#error':error, '#status':status, '#backend':backend,
    '#rate-preset':ratePreset, '#resolution-preset':resolutionPreset}[selector])};
for (const el of elements) el.focus = () => {document.activeElement=el;};
const posts = [];
let hold = null, fail = false, backendName;
const context = vm.createContext({document, queueMicrotask, setInterval:()=>{}, fetch:async(path,options)=>{
  if (options?.method === 'POST') {
    const patch = JSON.parse(options.body); posts.push(patch);
    if (hold) await hold;
    if (fail) { fail = false; return {ok:false, status:503, json:async()=>({error:'Injected failure'})}; }
    server = {...server, ...patch, generation:server.generation+1};
  }
  const body = path === '/api/health' ? {status:'running', clients:0, config:server, generated:1,
    deadline_misses:0, mailbox_drops:0, output:'test', backend:backendName} : server;
  return {ok:true, json:async()=>JSON.parse(JSON.stringify(body))};
}});
const field = name => elements.find(el=>el.name===name);
const edit = (name,value) => {const el=field(name);el.value=String(value);listeners.input({target:el});};
const choose = (preset,value) => {preset.value=value;preset.listeners.change();};
const refresh = () => vm.runInContext('health()', context);
const submit = () => form.onsubmit({preventDefault(){}});
(async()=>{
  vm.runInContext(SOURCE_SCRIPT, context);
  await new Promise(setImmediate);
  assert.equal(backend.textContent, 'Python · shared deterministic source');
  assert.equal(ratePreset.value, '30'); assert.equal(resolutionPreset.value, '512x512');
  server = {...server, view:'waveform', generation:2};
  await refresh(); assert.equal(field('view').value, 'waveform');
  edit('hz',60); document.activeElement=field('hz');
  server = {...server, hz:90, width:1024, generation:3};
  await refresh(); assert.equal(field('hz').value,'60'); assert.equal(field('width').value,1024);
  document.activeElement=null;
  await submit(); assert.deepEqual(posts.at(-1),{hz:60});
  assert.equal(server.view,'waveform'); assert.equal(server.width,1024);
  edit('width',256);
  let release; hold=new Promise(resolve=>release=resolve);
  const pending=submit(); edit('width',1024); release(); await pending; hold=null;
  assert.deepEqual(posts.at(-1),{width:256}); assert.equal(field('width').value,'1024');
  assert.equal(button.disabled,false); await submit(); assert.deepEqual(posts.at(-1),{width:1024});
  assert.equal(server.view,'waveform'); assert.equal(button.disabled,true);
  edit('height',256); fail=true; await submit(); assert.equal(error.textContent,'Injected failure');
  assert.equal(button.disabled,false); await submit(); assert.deepEqual(posts.at(-1),{height:256});
  edit('view','both'); await submit(); assert.deepEqual(posts.at(-1),{view:'both'});
  backendName='rust'; await refresh(); assert.equal(backend.textContent,'Rust · shared deterministic source');

  // Presets stage only numeric fields and survive polls alongside unrelated edits.
  server = {...server, view:'waveform', generation:server.generation+1}; await refresh();
  const postCount=posts.length;
  choose(ratePreset,'120'); choose(resolutionPreset,'1920x1080'); edit('seed',7);
  assert.equal(posts.length,postCount); assert.equal(button.disabled,false);
  server = {...server, hz:15, width:2048, height:2048, generation:server.generation+1};
  await refresh();
  assert.equal(ratePreset.value,'120'); assert.equal(resolutionPreset.value,'1920x1080');
  await submit(); assert.deepEqual(posts.at(-1),{hz:120,width:1920,height:1080,seed:7});
  assert.equal(server.view,'waveform'); assert.equal(button.disabled,true);

  // Custom does not send or dirty anything; manual values determine the selection.
  choose(ratePreset,''); choose(resolutionPreset,'');
  assert.equal(button.disabled,true); assert.equal(document.activeElement,field('width'));
  edit('hz',27.5); edit('width',800); edit('height',600);
  assert.equal(ratePreset.value,''); assert.equal(resolutionPreset.value,'');
  edit('hz',30); edit('width',512); edit('height',512);
  assert.equal(ratePreset.value,'30'); assert.equal(resolutionPreset.value,'512x512');
  document.activeElement=null; await submit();

  // A second preset chosen during Apply must survive the first response.
  choose(ratePreset,'60'); choose(resolutionPreset,'256x256');
  hold=new Promise(resolve=>release=resolve);
  const firstPreset=submit();
  choose(ratePreset,'30'); choose(resolutionPreset,'512x512');
  release(); await firstPreset; hold=null;
  assert.deepEqual(posts.at(-1),{hz:60,width:256,height:256});
  assert.equal(ratePreset.value,'30'); assert.equal(resolutionPreset.value,'512x512');
  assert.equal(button.disabled,false); await submit();
  assert.deepEqual(posts.at(-1),{hz:30,width:512,height:512});
  assert.equal(server.view,'waveform'); assert.equal(button.disabled,true);

  // External custom and preset configurations update pristine dropdowns.
  server={...server,hz:0.5,width:800,height:600,generation:server.generation+1}; await refresh();
  assert.equal(ratePreset.value,''); assert.equal(resolutionPreset.value,'');
  server={...server,hz:90,width:3840,height:2160,generation:server.generation+1}; await refresh();
  assert.equal(ratePreset.value,'90'); assert.equal(resolutionPreset.value,'3840x2160');
  document.activeElement=ratePreset;
  server={...server,hz:60,generation:server.generation+1}; await refresh();
  assert.equal(ratePreset.value,'90');
  document.activeElement=null; listeners.focusout(); await new Promise(setImmediate);
  assert.equal(ratePreset.value,'60'); assert.equal(button.disabled,true);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [
            node,
            "-e",
            f"const SOURCE_HTML = {json.dumps(html)};\n"
            f"const SOURCE_SCRIPT = {json.dumps(script)};\n{harness}",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
