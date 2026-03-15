function doGet(e) {
  if (!e.parameter.action) {
    return HtmlService.createHtmlOutputFromFile('Index')
      .setTitle('Vital Vortex')
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  }
  return handleRequest(e);
}

function doPost(e) { return handleRequest(e); }

function handleRequest(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const body = e.postData ? JSON.parse(e.postData.contents) : {};
  const action = e.parameter.action || body.action || '';

  if (action === 'read') {
    const sheet = ss.getSheetByName('Menu') || ss.getSheets()[0];
    const data = sheet.getDataRange().getValues();
    const headers = data[0];
    const rows = data.slice(1).filter(r => r[0] !== '').map(r => {
      const obj = {}; headers.forEach((h,i) => obj[h] = r[i]); return obj;
    });
    return out({ok:true, foods:rows});
  }

  if (action === 'write') {
    const sheet = ss.getSheetByName('Menu') || ss.getSheets()[0];
    sheet.clearContents();
    sheet.appendRow(['id','name','portion','cal','fat','carb','sugar','fiber','protein']);
    body.foods.forEach(f => sheet.appendRow([f.id,f.name,f.portion,f.cal,f.fat,f.carb,f.sugar,f.fiber,f.protein]));
    return out({ok:true});
  }

  if (action === 'saveplan') {
    let sheet = ss.getSheetByName('Plan');
    if (!sheet) sheet = ss.insertSheet('Plan');
    sheet.clearContents();
    sheet.getRange(1,1).setValue(body.blob);
    return out({ok:true});
  }

  if (action === 'loadplan') {
    const sheet = ss.getSheetByName('Plan');
    if (!sheet) return out({ok:true, blob:null});
    const blob = sheet.getRange(1,1).getValue();
    return out({ok:true, blob: blob || null});
  }

  if (action === 'log') {
    let sheet = ss.getSheetByName('Daily Log');
    if (!sheet) { sheet = ss.insertSheet('Daily Log'); sheet.appendRow(['date','cal','fat','carb','sugar','fiber','protein','water']); }
    const data = sheet.getDataRange().getValues();
    const existing = data.findIndex(r => r[0] === body.date);
    const row = [body.date, body.entry.cal, body.entry.fat, body.entry.carb, body.entry.sugar, body.entry.fiber, body.entry.protein, body.entry.water];
    if (existing > 0) sheet.getRange(existing+1,1,1,8).setValues([row]);
    else sheet.appendRow(row);
    return out({ok:true});
  }

  if (action === 'readlog') {
    const sheet = ss.getSheetByName('Daily Log');
    if (!sheet) return out({ok:true, log:{}});
    const data = sheet.getDataRange().getValues();
    const log = {};
    data.slice(1).forEach(r => { if(r[0]) log[r[0]] = {cal:r[1],fat:r[2],carb:r[3],sugar:r[4],fiber:r[5],protein:r[6],water:r[7]}; });
    return out({ok:true, log});
  }

  return out({ok:false, error:'unknown action: '+action});
}

function out(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.TEXT);
}