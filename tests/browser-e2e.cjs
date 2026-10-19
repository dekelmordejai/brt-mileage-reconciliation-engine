// Ejecutar contra una instancia local con base DEMO vacía e inicializada.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.MOTOR_BROWSER_CHANNEL||undefined});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[]; page.on('pageerror',e=>errors.push(e.message));
 const base=process.env.MOTOR_TEST_URL||'http://127.0.0.1:8766';
 for(let attempt=0;attempt<30;attempt++){try{const r=await fetch(base+'/healthz');if(r.ok)break;}catch{}if(attempt===29)throw new Error('El servidor local no está listo');await new Promise(resolve=>setTimeout(resolve,1000));}
 async function login(user){await page.locator('#login').getByLabel('Usuario',{exact:true}).fill(user);await page.locator('#login').getByLabel('Contraseña',{exact:true}).fill('Demo-local-2026!');await page.getByRole('button',{name:'Entrar a la mesa'}).click();await page.getByRole('button',{name:'Salir',exact:true}).waitFor();}
 async function logout(){await page.getByRole('button',{name:'Salir',exact:true}).click();await page.getByRole('button',{name:'Entrar a la mesa'}).waitFor();}
 await page.goto(base);await login('demo-admin');
 await page.getByRole('button',{name:'02 · Fuentes e importación'}).click();
 const fixture=JSON.parse(fs.readFileSync('fixtures/synthetic.json','utf8'));
 await page.locator('#upload').getByLabel('Archivo CSV, XLSX o JSON').setInputFiles({name:'RV-ui.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(fixture.RV))});
 await page.getByRole('button',{name:'Validar e importar'}).click();
 await page.getByText('Fuente conservada. 0 filas inválidas.').waitFor();
 await page.getByRole('button',{name:'Procesar conciliación',exact:true}).click();
 await page.getByText('Ejecución guardada. Los pendientes requieren revisión.').waitFor();
 await page.getByLabel('Buscar',{exact:true}).fill('DEMO-001');await page.getByRole('button',{name:'Buscar',exact:true}).click();
 await page.getByRole('button',{name:'Abrir',exact:true}).first().click();
 await page.getByRole('heading',{name:'Expediente del viaje'}).waitFor();
 await page.getByLabel('Origen físico').fill('Terminal A');await page.getByLabel('Destino físico').fill('Terminal C');
 const options=await page.locator('select.evidence option').all();assert(options.length>=2,'Falta evidencia Pasos');
 const value=await options[1].getAttribute('value');await page.locator('select.evidence').selectOption(value);
 await page.getByLabel('Motivo',{exact:true}).fill('Validación sintética del recorrido completo');
 await page.getByLabel('Referencia documental y alcance autorizado').fill('QA navegador sintético: terminales y distancia revisadas');
 await page.getByRole('button',{name:'Enviar propuesta a revisión'}).click();
 await page.getByText('Propuesta registrada. Requiere decisión de otra persona.').waitFor();
 await logout();await login('demo-revisor');
 await page.getByRole('button',{name:'03 · Propuestas y revisión'}).click();
 await page.getByLabel('Motivo de la decisión').first().fill('Segunda persona confirma evidencia sintética');
 await page.getByRole('button',{name:'Aprobar propuesta',exact:true}).first().click();
 await page.getByText('Decisión guardada. Procesa una ejecución nueva para reflejarla.').waitFor();
 await logout();await login('demo-admin');
 await page.getByRole('button',{name:'02 · Fuentes e importación'}).click();await page.getByRole('button',{name:'Procesar conciliación',exact:true}).click();
 await page.getByText('Ejecución guardada. Los pendientes requieren revisión.').waitFor();
 await page.locator('#kpis').getByText('102.50',{exact:false}).waitFor();
 const downloadPromise=page.waitForEvent('download');await page.getByRole('link',{name:'Descargar Excel'}).click();const download=await downloadPromise;assert(download.suggestedFilename().endsWith('.xlsx'));
 await page.getByRole('button',{name:'04 · Bitácora'}).click();await page.getByText(/Cadena íntegra/).waitFor();
 await page.getByRole('button',{name:'01 · Mesa de análisis'}).click();
 fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/dashboard-synthetic.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'test-results/mobile-synthetic.png',fullPage:true});
 assert.equal(errors.length,0,errors.join('\n'));await browser.close();console.log('E2E navegador: ejecución, búsqueda, expediente, propuesta, segunda persona, reproceso, Excel y auditoría. OK');
})().catch(e=>{console.error(e);process.exit(1);});
