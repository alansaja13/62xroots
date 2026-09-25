const {test} = require('node:test');
const assert = require('node:assert/strict');
const {drain, Store} = require('../static/growlog/offline-store.js');

const pending = () => ({payload:{id:'operation-123', datos:{notas:'Nota privada'}}, status:'pending'});
const success = () => ({status:201, body:{ok:true, data:{id:'operation-123', registro_id:5}}});

test('un timeout conserva pendiente y reutiliza UUID en el reintento', async () => {
  const item = pending(), saved = [], ids = [];
  const args = {items:[item], isCurrent:()=>true, save:async value=>saved.push(value)};
  assert.equal(await drain({...args, send:async payload=>{ids.push(payload.id); throw new Error('timeout');}}), 'offline');
  assert.equal(saved.length, 0);
  await drain({...args, send:async payload=>{ids.push(payload.id); return success();}});
  assert.deepEqual(ids, ['operation-123','operation-123']);
  assert.equal(saved[0].status, 'confirmed');
});

test('un acuse incompleto o HTML de login no confirma ni borra', async () => {
  for (const response of [{status:200, body:null}, {status:201,body:{ok:true,data:{id:'otra'}}}]) {
    const saved = [];
    assert.equal(await drain({items:[pending()], send:async()=>response, save:async value=>saved.push(value), isCurrent:()=>true}), 'offline');
    assert.equal(saved.length,0);
  }
});

test('permiso revocado y validación fallida conservan contenido con estado de revisión', async () => {
  for (const status of [400,403,404,409]) {
    const saved = [];
    await drain({items:[pending()], send:async()=>({status,body:{ok:false,error:'Revisar'}}), save:async value=>saved.push(value), isCurrent:()=>true});
    assert.equal(saved[0].status,'blocked');
    assert.equal(saved[0].payload.datos.notas,'Nota privada');
    assert.equal(saved[0].httpStatus,status);
  }
});

test('sesión vencida detiene el lote sin modificar los pendientes', async () => {
  let calls=0;
  assert.equal(await drain({items:[pending(),pending()], send:async()=>{calls++;return {status:401};}, save:async()=>assert.fail(), isCurrent:()=>true}), 'auth');
  assert.equal(calls,1);
});

test('cambio de cuenta durante envío no confirma datos en otra sesión', async () => {
  let active=true;
  const result = await drain({items:[pending()], send:async()=>{active=false;return success();}, save:async()=>assert.fail(), isCurrent:()=>active});
  assert.equal(result,'account');
});

test('no reenvía confirmados ni conflictos sin revisión explícita', async () => {
  await drain({items:[{...pending(),status:'confirmed'},{...pending(),status:'blocked'}], send:async()=>assert.fail(), save:async()=>assert.fail(), isCurrent:()=>true});
});

test('fallo al persistir confirmación deja disponible el reintento seguro', async () => {
  await assert.rejects(drain({items:[pending()],send:async()=>success(),save:async()=>{throw new Error('quota');},isCurrent:()=>true}),/quota/);
});

test('el contenido cifrado no expone notas y una clave ajena no lo abre', async () => {
  // Probar el cifrado real, sin simular AES. La persistencia se verifica en navegador.
  const store = Object.create(Store.prototype);
  store.identity = {user:'1'};
  store.key = crypto.subtle.generateKey({name:'AES-GCM',length:256},false,['encrypt','decrypt']);
  const row = await store.encrypt('item:1', pending());
  assert.equal(JSON.stringify(row).includes('Nota privada'),false);
  assert.deepEqual(await store.decrypt(row),pending());
  const other = Object.create(Store.prototype);
  other.key = crypto.subtle.generateKey({name:'AES-GCM',length:256},false,['encrypt','decrypt']);
  await assert.rejects(other.decrypt(row));
  await assert.rejects(store.decrypt({...row,id:'2:item:1'}));
});
