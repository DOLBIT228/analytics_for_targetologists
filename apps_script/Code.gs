const WEB_APP_TOKEN = 'replace-with-strong-random-token';

function jsonResponse(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents || '{}');

    if (!body.token || body.token !== WEB_APP_TOKEN) {
      return jsonResponse({ ok: false, error: 'unauthorized' });
    }

    const spreadsheetId = body.spreadsheet_id;
    const sheetName = body.sheet_name;
    const columns = body.columns || [];
    const action = body.action;

    const ss = SpreadsheetApp.openById(spreadsheetId);
    const sheet = ss.getSheetByName(sheetName) || ss.insertSheet(sheetName);

    if (action === 'ensure_header') {
      const currentHeader = sheet.getRange(1, 1, 1, columns.length).getValues()[0];
      const same = JSON.stringify(currentHeader) === JSON.stringify(columns);
      if (!same) {
        sheet.getRange(1, 1, 1, columns.length).setValues([columns]);
      }
      return jsonResponse({ ok: true });
    }

    if (action === 'load_sheet_data') {
      const lastRow = sheet.getLastRow();
      if (lastRow <= 1) {
        return jsonResponse({ ok: true, rows: [], index: {} });
      }

      const width = columns.length;
      const values = sheet.getRange(2, 1, lastRow - 1, width).getValues();
      const rows = values.map((arr) => {
        const obj = {};
        columns.forEach((col, i) => obj[col] = arr[i]);
        return obj;
      });

      const index = {};
      rows.forEach((row, i) => {
        const dealId = String(row.deal_id || '').trim();
        if (dealId) {
          index[dealId] = i + 2;
        }
      });

      return jsonResponse({ ok: true, rows: rows, index: index });
    }

    if (action === 'append_rows') {
      const rows = body.rows || [];
      if (rows.length > 0) {
        const values = rows.map((row) => columns.map((col) => row[col] || ''));
        const startRow = sheet.getLastRow() + 1;
        sheet.getRange(startRow, 1, values.length, columns.length).setValues(values);
      }
      return jsonResponse({ ok: true });
    }

    if (action === 'update_row') {
      const rowNumber = Number(body.row_number);
      const rowData = body.row_data || {};
      const values = columns.map((col) => rowData[col] || '');
      sheet.getRange(rowNumber, 1, 1, columns.length).setValues([values]);
      return jsonResponse({ ok: true });
    }

    if (action === 'delete_rows') {
      const rowNumbers = (body.row_numbers || [])
        .map((v) => Number(v))
        .filter((v) => Number.isFinite(v) && v >= 2)
        .sort((a, b) => b - a);

      rowNumbers.forEach((rowNumber) => sheet.deleteRow(rowNumber));
      return jsonResponse({ ok: true, deleted: rowNumbers.length });
    }

    if (action === 'clear_data') {
      const lastRow = sheet.getLastRow();
      if (lastRow > 1) {
        sheet.getRange(2, 1, lastRow - 1, columns.length).clearContent();
      }
      return jsonResponse({ ok: true });
    }

    if (action === 'count_deals') {
      const count = Math.max(sheet.getLastRow() - 1, 0);
      return jsonResponse({ ok: true, count: count });
    }

    return jsonResponse({ ok: false, error: 'unknown_action' });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) });
  }
}
