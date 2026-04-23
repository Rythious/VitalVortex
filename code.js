function doGet(e) {
  if (!e.parameter.action) {
    return HtmlService.createHtmlOutputFromFile('Index')
      .setTitle('Vital Vortex')
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
      .addMetaTag('viewport', 'width=device-width, initial-scale=1.0, maximum-scale=1.0');
  }
  const result = handleRequest(e);
  return ContentService.createTextOutput(JSON.stringify(result)).setMimeType(ContentService.MimeType.TEXT);
}

function doPost(e) {
  const result = handleRequest(e);
  return ContentService.createTextOutput(JSON.stringify(result)).setMimeType(ContentService.MimeType.TEXT);
}

// Called directly by google.script.run from the browser (deployed mode).
// Accepts a plain JS object with an 'action' property instead of a request object.
function handleRequest(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  // Support both: plain object from google.script.run, and HTTP request from doGet/doPost
  const body   = (e && e.postData) ? JSON.parse(e.postData.contents) : (e || {});
  const action = (e && e.parameter && e.parameter.action) || body.action || '';

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
    // Deduplicate by ID to prevent duplicate menu items when syncing
    const seen = new Set();
    const unique = body.foods.filter(f => {
      if (seen.has(f.id)) return false;
      seen.add(f.id);
      return true;
    });
    unique.forEach(f => sheet.appendRow([f.id,f.name,f.portion,f.cal,f.fat,f.carb,f.sugar,f.fiber,f.protein]));
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
    if (!sheet) {
      sheet = ss.insertSheet('Daily Log');
      sheet.appendRow(['date','cal','fat','carb','sugar','fiber','protein','water']);
    }
    // Force column A to plain text so Google Sheets never auto-converts dates.
    sheet.getRange('A:A').setNumberFormat('@');
    const data = sheet.getDataRange().getValues();
    // Normalize each row's date key the same way readlog does, so the findIndex match works
    // even for any old rows that were stored as Date objects before this fix.
    const existing = data.findIndex(r => {
      if (!r[0]) return false;
      const k = r[0] instanceof Date
        ? r[0].getFullYear() + '-' + String(r[0].getMonth()+1).padStart(2,'0') + '-' + String(r[0].getDate()).padStart(2,'0')
        : String(r[0]).trim();
      return k === body.date;
    });
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
    data.slice(1).forEach(r => {
      if (!r[0]) return;
      // r[0] may be a Date object if Google Sheets auto-converted the column.
      // Normalize it to YYYY-MM-DD regardless of how it's stored.
      let dateKey;
      if (r[0] instanceof Date) {
        const y = r[0].getFullYear();
        const m = String(r[0].getMonth() + 1).padStart(2, '0');
        const d = String(r[0].getDate()).padStart(2, '0');
        dateKey = y + '-' + m + '-' + d;
      } else {
        // Already a string — normalize M/D/YYYY → YYYY-MM-DD just in case
        const s = String(r[0]).trim();
        if (s.includes('/')) {
          const parts = s.split('/');
          const mo = parts[0].padStart(2,'0');
          const dy = parts[1].padStart(2,'0');
          const yr = parts[2].length === 2 ? '20' + parts[2] : parts[2];
          dateKey = yr + '-' + mo + '-' + dy;
        } else {
          dateKey = s;
        }
      }
      log[dateKey] = {cal:r[1], fat:r[2], carb:r[3], sugar:r[4], fiber:r[5], protein:r[6], water:r[7]};
    });
    return out({ok:true, log});
  }

  return out({ok:false, error:'unknown action: '+action});
}

function out(obj) {
  // When called via google.script.run, return a plain object.
  // When called via doGet/doPost (HTTP), return a ContentService response.
  // We detect the context by checking if ContentService is being used in an HTTP request.
  // Since handleRequest is called both ways, always return plain obj —
  // doGet/doPost callers won't use the return value directly anyway in this app.
  return obj;
}