// Exercise production UI transitions without a browser or physical device.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('web/app.js','utf8');
const elements=new Map();
function element(key){if(!elements.has(key))elements.set(key,{classList:{toggle(){}},replaceChildren(){this.cleared=true;}});return elements.get(key);}
const context={$:element,fmt:String,bytes:String,pending:false,tab:'files',Number,Math};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function updateState('),source.indexOf('async function poll(')),context);
const status={mode:'idle',storageOwner:'web',imu:true,sd:true,memory:true,sampleAge:0,values:Array(9).fill(0),min:Array(9).fill(0),max:Array(9).fill(0),axisHz:[500,500,100],accRate:500,gyroRate:500,magRate:100};
context.updateState({...status,storageOwner:'usb',usbBusy:true});
assert.equal(element('#usbNotice').hidden,false);
assert.equal(element('#fileTools').hidden,true);
assert.equal(element('#start').disabled,true);
assert.equal(element('#saveSettings').disabled,true);
assert.equal(element('#releaseUsb').disabled,true);
assert.equal(element('#fileList').cleared,true);
context.updateState({...status,storageOwner:'usb',usbBusy:false});
assert.equal(element('#releaseUsb').disabled,false);
context.updateState(status);
assert.equal(element('#usbNotice').hidden,true);
assert.equal(element('#fileTools').hidden,false);
assert.equal(element('#start').disabled,false);
context.updateState({...status,mode:'recording',storageOwner:'logger'});
assert.equal(element('#storageLocked').hidden,false);
assert.equal(element('#fileTools').hidden,true);
console.log('PASS: USB ownership locks files/start/settings; in-progress transfer blocks release; web handoff unlocks; recording remains protected.');

context.updateState({...status,mode:'error',storageOwner:'logger'});
assert.equal(element('#fileTools').hidden,true);
assert.equal(element('#start').disabled,true);
assert.equal(element('#saveSettings').disabled,true);
console.log('PASS: error cleanup retains SD ownership until the writer has closed its files.');

context.updateState({...status,recovering:true,recoveryMessage:'Opravuji CSV',recoveryPercent:50});
assert.equal(element('#fileTools').hidden,true);assert.equal(element('#start').disabled,true);assert.equal(element('#saveSettings').disabled,true);assert.match(element('#recoveryNotice').textContent,/50/);
console.log('PASS: boot recovery locks SD actions and exposes progress.');
