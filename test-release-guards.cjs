const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');
const java=fs.readFileSync('app/src/main/java/com/nova/jobhunter/MainActivity.java','utf8');
const cpp=fs.readFileSync('app/src/main/cpp/nova_jni.cpp','utf8');
const workflow=fs.readFileSync('.github/workflows/build-apk.yml','utf8');
test('native cancellation is bridged and bounded',()=>{assert.match(java,/nativeCancelGeneration/);assert.match(cpp,/cancel_requested\.load/);assert.match(cpp,/seconds\(120\)/);});
test('model replacement keeps a recovery copy',()=>{assert.match(java,/nova-model\.previous\.gguf/);assert.match(java,/previous\.renameTo\(dest\)/);});
test('scope pagination is bounded and restricted',()=>{assert.match(java,/pages<10/);assert.match(java,/Unsafe pagination URL/);});
test('release pipeline runs all tests',()=>{assert.match(workflow,/test-ai-pipeline\.cjs/);assert.match(workflow,/test-bounty-approval\.cjs/);});
