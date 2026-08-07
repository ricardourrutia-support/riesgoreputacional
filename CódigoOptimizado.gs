/**************************************************************************************************
 * [CL] Airport Performance · Coordinators & Fleets — v4.1 (carga optimizada)
 * Base de datos: "Desempeño coordinadores" (solo hojas de data cargadas por el Sapineitor)
 *
 * Cambios v4 (sobre v3):
 *  1. ADIÓS HOJA "Desempeño": era una hoja calculada y ya no existe. Los turnos ahora se leen
 *     DIRECTO del archivo TURNOS 360 (hojas "Coordinadores <Mes>"), se expanden a franjas de
 *     1 hora y se EXCLUYEN las franjas administrativas por hora de ingreso. Esa exclusión, que
 *     antes hacía el Sapineitor al escribir Desempeño, ahora vive acá.
 *  2. El mapa de turnos se cachea (30 min) en formato compacto, así el archivo de turnos no se
 *     abre en cada request.
 *  3. FIX Conexiones: la hoja ya no trae las columnas calculadas 'Patente' ni 'Producto'.
 *     Se usa 'Reg Plate' y el producto se deduce del sufijo (N)/(C) de la patente.
 *  4. PERFORMANCE
 *     - getCellDetail lee POR BANDA: primero ubica el rango de filas del bloque con las
 *       columnas de fecha/hora, y solo entonces lee el resto de columnas de esas filas.
 *       ~2.6x menos celdas transferidas por clic.
 *     - getCellDetail se cachea 5 min por bloque.
 *     - Rango seleccionable configurable (MESES_HISTORIA) y vista por defecto acotada
 *       (DEFAULT_DIAS) para que la primera carga sea liviana.
 *     - precalentarCache(): función para dejar el resumen caliente vía trigger, idealmente
 *       justo después de que corra el Sapineitor.
 *  5. ROBUSTEZ: si Turnos 360 no está accesible, el dashboard sigue funcionando sin la capa
 *     de coordinadores y avisa en la UI (antes reventaba al no encontrar la hoja).
 *  6. PERFORMANCE v4.1 (sin cambiar cálculos ni resultados):
 *     - Carga inicial en una sola llamada servidor (configuración + resumen).
 *     - Huella de hojas cacheada 5 min; ↻ Recalcular la fuerza a actualizar.
 *     - Caché JSON fragmentado: también guarda respuestas mayores a 100 KB.
 *     - Precalentamiento reconstruye Turnos 360 una sola vez.
 *
 * REQUISITO: timezone del proyecto = America/Santiago (appsscript.json -> "timeZone").
 **************************************************************************************************/

const SHEET_ID = '1hlQTgK3WS0y8Vs4lP_xYbuGJSSLcXwh1Y996lTuYJXY';

/* Filtro de rescates por cliente. Deja '' para desactivarlo. */
const RESCATE_CLIENT_ID = 'd108ff27d3f858d229c6624e4804398e';

const CACHE_TTL_SEC = 300;        // resumen y detalle: 5 min
const CACHE_TTL_SHIFT = 1800;     // turnos: 30 min (cambian poco; ↻ Recalcular los refresca)
const CACHE_TTL_FINGERPRINT = 300; // huella de tamaños: 5 min (mismo horizonte que el resumen)
const CACHE_CHUNK_CHARS = 60000;   // margen seguro bajo el límite de 100 KB por entrada
const CACHE_KEY_FINGERPRINT = 'airport_data_fingerprint_v1';

/* Rango seleccionable: mes en curso + N meses hacia atrás. */
const MESES_HISTORIA = 2;

/* Vista por defecto al abrir: últimos N días (carga liviana y siempre con data). */
const DEFAULT_DIAS = 14;

/* ---- Turnos 360: única fuente de turnos de coordinadores ---- */
const TURNOS = {
  spreadsheetId: '1xepmv4-ocTNZ-RXBa7pFBXp4KM56ZTrAgeO5M0B7yCg',

  /* Solo hojas "Coordinadores <Mes>". Agentes / Anfitriones / Supervisores se ignoran. */
  prefix: 'Coordinadores',

  /* Franjas administrativas por hora de ingreso: NO comisionan y por lo tanto
     el coordinador NO se considera a cargo del bloque en esas horas. */
  adminPorIngreso: {
    5:  [11, 12, 13],   // 05:00 → 16:00
    10: [10, 14, 15],   // 10:00 → 21:00
    13: [17, 18, 19],   // 13:00 → 00:00
    21: [6, 7, 8]       // 21:00 → 08:00
  }
};

const SH = {
  LOSA:    'KPI 2 Time Loza',
  JOURNEY: 'KPI 3 Time DO',
  PICKUP:  'KPI 4 Time Pick Up',
  RESCATE: 'Rescates',
  DOX:     'Doxproductname',
  PROG:    'Programación Turnos & Patentes',
  /* Acepta ambos nombres (con y sin "s" final) */
  CONEX:   ['Registro de Conexiones Efectivas', 'Registro de Conexiones Efectiva']
};

const COL = {
  losaSeg: 'Segmento Tiempo en Losa',
  losaTs:  'tm_start_local_at',
  jrnSeg:  'Segment Duration',
  jrnTs:   'Start At Local Dttm',
  jrnDir:  'Desde / Hacia Aeropuerto',
  pkpSeg:  'Segment Arrived to Pickup vs Requested',
  pkpTs:   'Start At Local Dttm',
  pkpDir:  'Desde / Hacia Aeropuerto',
  resTs:   'Start At Local Dttm',
  resClient: 'Client Id',

  conexDate:      'Date',
  conexHour:      'Hora de Time',
  conexPlate:     'Reg Plate',      // ' VBTX61 (N)' — el producto sale del sufijo
  conexCompany:   'Company Name',   // fallback: 'company'
  conexCompanyFb: 'company',
  conexDriver:    'Driver Name',
  conexTariff:    'Tariff Name',
  conexWH:        'Working Hours',
  conexWHB:       'Working Hours Busy',

  progDate:   'Fecha de Operación',
  progHour:   'Hora',
  progPlate:  'Patente',            // cruda: ' [VBTX53]' -> se normaliza
  progFleet:  'Fleets Aeropuerto',
  progBloque: 'Bloque Asignado'
};

/* ------------------------------------------------------------------ Web app entry */
function doGet() {
  return HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('[CL] Airport Performance · Coordinators & Fleets')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}
function include(file) {
  return HtmlService.createHtmlOutputFromFile(file).getContent();
}

/* ------------------------------------------------------------------ Acceso a datos */
var _SS_ = null;
var _TBL_ = {};

function _ss() {
  if (!_SS_) _SS_ = SpreadsheetApp.openById(SHEET_ID);
  return _SS_;
}

function _sheet(nameOrList) {
  var names = Array.isArray(nameOrList) ? nameOrList : [nameOrList];
  for (var i = 0; i < names.length; i++) {
    var sh = _ss().getSheetByName(names[i]);
    if (sh) return sh;
  }
  throw new Error('No se encontró la hoja: "' + names.join('" ni "') + '"');
}

function _tbl(nameOrList) {
  var key = Array.isArray(nameOrList) ? nameOrList[0] : nameOrList;
  if (_TBL_[key]) return _TBL_[key];
  var sh = _sheet(nameOrList);
  var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
  var header = (lastRow > 0 && lastCol > 0) ? sh.getRange(1, 1, 1, lastCol).getValues()[0] : [];
  var hmap = {};
  header.forEach(function (h, i) { if (h !== '' && h != null) hmap[String(h).trim()] = i; });
  return (_TBL_[key] = { sh: sh, name: key, n: Math.max(0, lastRow - 1), hmap: hmap, cols: {} });
}

/* Lee UNA columna completa (solo la primera vez por ejecución). */
function _col(t, name, required) {
  if (name in t.cols) return t.cols[name];
  if (!(name in t.hmap)) {
    if (required) throw new Error('Falta la columna "' + name + '" en la hoja "' + t.name + '"');
    return (t.cols[name] = null);
  }
  if (t.n === 0) return (t.cols[name] = []);
  var v = t.sh.getRange(2, t.hmap[name] + 1, t.n, 1).getValues();
  var arr = new Array(t.n);
  for (var i = 0; i < t.n; i++) arr[i] = v[i][0];
  return (t.cols[name] = arr);
}

/* Lee un TRAMO de una columna (lectura por banda). start es índice 0-based de data.
   Devuelve un array de largo count; el elemento i corresponde a la fila start + i. */
function _colBand(t, name, start, count) {
  if (!(name in t.hmap) || count <= 0) return null;
  if (name in t.cols && t.cols[name]) {            // ya está completa en memoria
    return t.cols[name].slice(start, start + count);
  }
  var v = t.sh.getRange(2 + start, t.hmap[name] + 1, count, 1).getValues();
  var arr = new Array(count);
  for (var i = 0; i < count; i++) arr[i] = v[i][0];
  return arr;
}

/* Rango de filas [start, count] que contiene TODAS las filas del bloque (dk, hr).
   Puede incluir filas de otros bloques: quien la use debe re-filtrar. */
function _band(t, dk, hr, opt) {
  var lo = -1, hi = -1, r, d;
  if (opt.ts) {
    var ts = _col(t, opt.ts, true);
    for (r = 0; r < t.n; r++) {
      d = _toDate(ts[r]); if (!d) continue;
      if (_dk(d) !== dk || d.getHours() !== hr) continue;
      if (lo < 0) lo = r;
      hi = r;
    }
  } else {
    var dt = _col(t, opt.date, true), hh = _col(t, opt.hour, true);
    for (r = 0; r < t.n; r++) {
      d = _toDate(dt[r]); if (!d) continue;
      if (_dk(d) !== dk) continue;
      if (Math.round(Number(hh[r])) !== hr) continue;
      if (lo < 0) lo = r;
      hi = r;
    }
  }
  if (lo < 0) return null;
  return { start: lo, count: hi - lo + 1 };
}

/* ------------------------------------------------------------------ Fecha / hora */
function _p2(n) { return (n < 10 ? '0' : '') + n; }
function _dk(d) { return d.getFullYear() + '-' + _p2(d.getMonth() + 1) + '-' + _p2(d.getDate()); }

function _toDate(v) {
  if (v instanceof Date && !isNaN(v)) return v;
  if (typeof v === 'string' && v.trim()) {
    var s = v.trim().replace(/\//g, '-');
    var d = new Date(s);
    if (!isNaN(d)) return d;
  }
  return null;
}

/* Patente normalizada para cruzar Programación ↔ Conexiones:
   ' [VBTX53]' -> 'VBTX53' · 'VBTY13 (N)' -> 'VBTY13' */
function _normPlate(v) {
  var s = String(v == null ? '' : v);
  s = s.replace(/\(([NCnc])\)/g, '');
  s = s.replace(/[\[\]\s]/g, '');
  return s.toUpperCase();
}

/* Producto a partir de la patente: 'VBTX61 (N)' -> 'N' */
function _prodOf(plate) {
  var m = String(plate || '').match(/\(([NCnc])\)/);
  return m ? m[1].toUpperCase() : 'X';
}

/* Límites seleccionables: [primer día de hace MESES_HISTORIA meses, hoy] */
function _monthBounds() {
  var now = new Date();
  var prev = new Date(now.getFullYear(), now.getMonth() - MESES_HISTORIA, 1);
  var def = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (DEFAULT_DIAS - 1));
  var min = _dk(prev);
  var defFrom = _dk(def);
  return {
    min: min,
    max: _dk(now),
    defFrom: (defFrom < min) ? min : defFrom
  };
}
function _clampToMonth(from, to) {
  var b = _monthBounds();
  from = (from && from >= b.min) ? from : b.min;
  to   = (to && to <= b.max) ? to : b.max;
  if (from > to) from = to;
  return { from: from, to: to };
}

/* ------------------------------------------------------------------ TURNOS 360 → mapa de turnos
   { map: {'YYYY-MM-DD|H': [coordinadores]}, coords: [...], error: '' }
   Las franjas administrativas ya vienen excluidas. */
var _SHIFT_ = null;

function _monthsInScope() {
  var b = _monthBounds();
  var out = [];
  var d = new Date(Number(b.min.substring(0, 4)), Number(b.min.substring(5, 7)) - 1, 1);
  var end = new Date(Number(b.max.substring(0, 4)), Number(b.max.substring(5, 7)) - 1, 1);
  /* un mes extra hacia atrás: captura el turno 21:00 del último día del mes previo,
     cuyas horas 0..5 caen dentro del rango */
  d = new Date(d.getFullYear(), d.getMonth() - 1, 1);
  while (d <= end) {
    out.push({ month: d.getMonth() + 1, year: d.getFullYear() });
    d = new Date(d.getFullYear(), d.getMonth() + 1, 1);
  }
  return out;
}

function _nombreMes(m) {
  return ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
          'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'][m - 1] || '';
}

function _norm(s) {
  return String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
}

function _shift(force) {
  if (_SHIFT_ && !force) return _SHIFT_;

  var cache = CacheService.getScriptCache();
  var months = _monthsInScope();
  var ckey = 'shift4_' + months.map(function (p) { return p.year + '-' + p.month; }).join('_');

  if (!force) {
    var hit = cache.get(ckey);
    if (hit) {
      try { return (_SHIFT_ = _unpackShift(JSON.parse(hit))); } catch (e) { /* sigue y reconstruye */ }
    }
  }

  var out = { map: {}, coords: [], error: '' };

  try {
    var ss = SpreadsheetApp.openById(TURNOS.spreadsheetId);
    var sheets = ss.getSheets();
    var asign = [];

    months.forEach(function (p) {
      var sh = _findCoordSheet(sheets, p.month);
      if (!sh) return;                     // mes sin planilla aún: no es error
      asign = asign.concat(_parseCoordSheet(sh, p.month, p.year));
    });

    out = _expandShifts(asign);

    if (!out.coords.length) {
      out.error = 'Turnos 360: no encontré turnos de coordinadores para el período.';
    }
  } catch (e) {
    out.error = 'No pude leer Turnos 360 (' + e.message + '). El dashboard funciona, ' +
                'pero sin desglose por coordinador.';
  }

  try { cache.put(ckey, JSON.stringify(_packShift(out)), CACHE_TTL_SHIFT); } catch (e) { /* muy grande */ }
  return (_SHIFT_ = out);
}

/* Formato compacto para caché: nombres indexados. */
function _packShift(s) {
  var idx = {}, names = s.coords.slice();
  names.forEach(function (n, i) { idx[n] = i; });
  var m = {};
  Object.keys(s.map).forEach(function (k) {
    m[k] = s.map[k].map(function (n) { return idx[n]; });
  });
  return { n: names, m: m, e: s.error || '' };
}
function _unpackShift(p) {
  var map = {};
  Object.keys(p.m).forEach(function (k) {
    map[k] = p.m[k].map(function (i) { return p.n[i]; });
  });
  return { map: map, coords: p.n, error: p.e || '' };
}

function _findCoordSheet(sheets, month) {
  var objetivo = _norm(TURNOS.prefix + ' ' + _nombreMes(month));
  var prefijo = _norm(TURNOS.prefix);
  var i;
  for (i = 0; i < sheets.length; i++) {
    if (_norm(sheets[i].getName()) === objetivo) return sheets[i];
  }
  for (i = 0; i < sheets.length; i++) {
    var n = _norm(sheets[i].getName());
    if (n.indexOf(prefijo) === 0 && n.indexOf(_norm(_nombreMes(month))) >= 0) return sheets[i];
  }
  return null;
}

/* Matriz mensual -> [{fecha, nombre, hIni, hFin}].
   - La fila de fechas se detecta (el layout cambia entre meses).
   - Solo cuentan las columnas cuya fecha es del mes/año pedido: las hojas traen
     semanas completas y se solapan en los bordes, así cada mes lo manda su hoja.
   - Celda válida = contiene 'H:MM - H:MM'. 'Libre', vacío, 'Vacaciones', etc. se ignoran. */
function _parseCoordSheet(sheet, month, year) {
  var values = sheet.getDataRange().getValues();
  if (values.length < 2) return [];

  var dateRow = -1, best = 0, i, j;
  for (i = 0; i < Math.min(values.length, 10); i++) {
    var n = 0;
    for (j = 1; j < values[i].length; j++) {
      if (values[i][j] instanceof Date && !isNaN(values[i][j].getTime())) n++;
    }
    if (n > best) { best = n; dateRow = i; }
  }
  if (dateRow < 0) return [];

  var fechaPorCol = {};
  for (j = 1; j < values[dateRow].length; j++) {
    var v = values[dateRow][j];
    if (v instanceof Date && !isNaN(v.getTime()) &&
        v.getMonth() + 1 === month && v.getFullYear() === year) {
      fechaPorCol[j] = new Date(v.getFullYear(), v.getMonth(), v.getDate());
    }
  }

  var re = /(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})/;
  var out = [];

  for (i = dateRow + 1; i < values.length; i++) {
    var nombre = String(values[i][0] || '').trim();
    if (!nombre || nombre === '.' || _norm(nombre) === 'nombre') continue;
    if (!/[a-záéíóúñ]/i.test(nombre)) continue;

    for (var c in fechaPorCol) {
      var m = String(values[i][c] || '').trim().match(re);
      if (!m) continue;
      out.push({
        fecha: fechaPorCol[c],
        nombre: nombre,
        hIni: Number(m[1]) % 24,
        hFin: Number(m[3]) % 24
      });
    }
  }
  return out;
}

/* Expande turnos a franjas de 1 h EFECTIVAS (sin franjas administrativas).
   Fin exclusivo: 05:00-16:00 -> 5..15. Cruce de medianoche: 21:00-08:00 -> 21..23 + 0..7 del
   día siguiente. Solo se guardan horas dentro de los límites seleccionables. */
function _expandShifts(asignaciones) {
  var b = _monthBounds();
  var map = {}, coordSet = {};

  asignaciones.forEach(function (a) {
    var admin = TURNOS.adminPorIngreso[a.hIni] || [];
    var adminSet = {};
    admin.forEach(function (h) { adminSet[h] = true; });

    var horas = [], h;
    if (a.hFin > a.hIni) {
      for (h = a.hIni; h < a.hFin; h++) horas.push({ off: 0, h: h });
    } else {
      for (h = a.hIni; h < 24; h++) horas.push({ off: 0, h: h });
      for (h = 0; h < a.hFin; h++) horas.push({ off: 1, h: h });
    }

    horas.forEach(function (x) {
      if (adminSet[x.h]) return;                      // franja administrativa -> no comisiona
      var dia = new Date(a.fecha.getFullYear(), a.fecha.getMonth(), a.fecha.getDate() + x.off);
      var dk = _dk(dia);
      if (dk < b.min || dk > b.max) return;

      var key = dk + '|' + x.h;
      var arr = map[key] || (map[key] = []);
      if (arr.indexOf(a.nombre) < 0) arr.push(a.nombre);
      coordSet[a.nombre] = true;
    });
  });

  return { map: map, coords: Object.keys(coordSet).sort(), error: '' };
}

/* ------------------------------------------------------------------ API: init */
function getInitData() {
  var shift = _shift(false);
  var b = _monthBounds();
  return {
    coords: shift.coords,
    shiftWarning: shift.error || '',
    dateMin: b.min, dateMax: b.max, defFrom: b.defFrom,
    hours: _allHours()
  };
}

/*
 * Carga inicial optimizada: configuración + resumen en UNA sola llamada desde el HTML.
 * getInitData() se mantiene para compatibilidad, pero Index.html usa esta función.
 */
function getInitialPayload() {
  var started = Date.now();
  var cfg = getInitData();
  var summary = getSummary({
    dateFrom: cfg.defFrom,
    dateTo: cfg.dateMax,
    hours: [],
    coordinator: '__ALL__',
    nocache: false,
    forceShift: false
  });
  Logger.log('🚀 Carga inicial completa en ' + (Date.now() - started) + ' ms');
  return { cfg: cfg, summary: summary };
}

/* ------------------------------------------------------------------ Caché */

/*
 * Huella de la data. Conserva la lógica original (filas x columnas), pero la guarda
 * durante el mismo tiempo que el resumen para no consultar seis hojas en cada request.
 * ↻ Recalcular usa force=true y vuelve a leer la huella inmediatamente.
 */
function _fingerprint(force) {
  var cache = CacheService.getScriptCache();
  if (!force) {
    var cached = cache.get(CACHE_KEY_FINGERPRINT);
    if (cached) return cached;
  }

  var names = [SH.LOSA, SH.JOURNEY, SH.PICKUP, SH.RESCATE, SH.PROG, SH.CONEX];
  var sizes = names.map(function (n) {
    try {
      var sh = _sheet(n);
      return sh.getLastRow() + 'x' + sh.getLastColumn();
    } catch (e) {
      return '0';
    }
  }).join('|');

  /* Versión opcional: marcarDatosActualizados() la cambia aunque el número de filas sea igual. */
  var manualVersion = PropertiesService.getScriptProperties().getProperty('DATA_VERSION') || '0';
  var fp = manualVersion + '|' + sizes;
  try { cache.put(CACHE_KEY_FINGERPRINT, fp, CACHE_TTL_FINGERPRINT); } catch (e) {}
  return fp;
}

function _ckey(prefix, parts) {
  return prefix + Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, JSON.stringify(parts)));
}

/* Lee JSON simple o fragmentado desde CacheService. */
function _cacheGetJson(cache, key) {
  var raw = cache.get(key);
  if (!raw) return null;

  try {
    var parsed = JSON.parse(raw);
    if (!parsed || parsed.__chunked__ !== 1) return parsed;

    var keys = [];
    for (var i = 0; i < parsed.chunks; i++) keys.push(key + ':c' + i);
    var pieces = cache.getAll(keys);
    var json = '';
    for (var j = 0; j < keys.length; j++) {
      if (!(keys[j] in pieces)) return null; // expiró o falta un fragmento
      json += pieces[keys[j]];
    }
    return JSON.parse(json);
  } catch (e) {
    Logger.log('⚠️ Caché inválida para ' + key + ': ' + e.message);
    return null;
  }
}

/* Guarda JSON incluso cuando supera 100 KB, dividiéndolo en entradas pequeñas. */
function _cachePutJson(cache, key, value, ttlSec) {
  var json = JSON.stringify(value);
  try {
    if (json.length <= CACHE_CHUNK_CHARS) {
      cache.put(key, json, ttlSec);
      return { ok: true, chunks: 1, chars: json.length };
    }

    var chunks = Math.ceil(json.length / CACHE_CHUNK_CHARS);
    var entries = {};
    for (var i = 0; i < chunks; i++) {
      entries[key + ':c' + i] = json.substring(
        i * CACHE_CHUNK_CHARS,
        (i + 1) * CACHE_CHUNK_CHARS
      );
    }
    cache.putAll(entries, ttlSec);
    cache.put(key, JSON.stringify({ __chunked__: 1, chunks: chunks }), ttlSec);
    return { ok: true, chunks: chunks, chars: json.length };
  } catch (e) {
    Logger.log('⚠️ No se pudo guardar caché ' + key + ': ' + e.message);
    return { ok: false, chunks: 0, chars: json.length };
  }
}

/*
 * Útil al terminar una carga del Sapineitor. Cambia la versión aunque las hojas
 * conserven exactamente la misma cantidad de filas y columnas.
 * Puede ejecutarse manualmente o llamarse al final del proceso de carga.
 */
function marcarDatosActualizados() {
  PropertiesService.getScriptProperties().setProperty('DATA_VERSION', String(Date.now()));
  CacheService.getScriptCache().remove(CACHE_KEY_FINGERPRINT);
  _SS_ = null;
  _TBL_ = {};
  _SHIFT_ = null;
  Logger.log('✅ Versión de datos actualizada.');
}

/* Deja el resumen inicial caliente. Ideal: ejecutar después del Sapineitor. */
function precalentarCache() {
  var b = _monthBounds();
  getSummary({
    dateFrom: b.defFrom,
    dateTo: b.max,
    hours: [],
    coordinator: '__ALL__',
    nocache: true,
    forceShift: true
  });
  Logger.log('✅ Caché precalentada: ' + b.defFrom + ' → ' + b.max);
}

/* ------------------------------------------------------------------ API: resumen + heatmap */
function getSummary(filters) {
  filters = filters || {};
  var started = Date.now();
  var cache = CacheService.getScriptCache();
  var forceData = !!filters.nocache;
  var key = _ckey('sum6_', [
    filters.dateFrom,
    filters.dateTo,
    filters.hours || [],
    filters.coordinator || '',
    _fingerprint(forceData)
  ]);

  if (!forceData) {
    var hit = _cacheGetJson(cache, key);
    if (hit) {
      Logger.log('✅ Summary cache HIT · ' + (Date.now() - started) + ' ms');
      return hit;
    }
  }

  var out = _computeSummary(filters, !!filters.forceShift);
  var saved = _cachePutJson(cache, key, out, CACHE_TTL_SEC);
  Logger.log('⚙️ Summary recalculado · ' + (Date.now() - started) + ' ms · ' +
    saved.chars + ' chars · ' + saved.chunks + ' fragmento(s)');
  return out;
}

function _computeSummary(filters, forceShift) {
  var rng = _clampToMonth(filters.dateFrom, filters.dateTo);
  var from = rng.from, to = rng.to;

  var hoursSel = (filters.hours && filters.hours.length) ? filters.hours.map(Number) : null;
  var hoursSet = null;
  if (hoursSel) { hoursSet = {}; hoursSel.forEach(function (x) { hoursSet['h' + x] = true; }); }
  var coord = (filters.coordinator && filters.coordinator !== '__ALL__') ? filters.coordinator : null;

  var shift = _shift(forceShift);
  var shiftMap = shift.map;

  var losaW = 0, losaT = 0, jrnW = 0, jrnT = 0, pkpW = 0, pkpT = 0, res = 0, whbTot = 0;
  var jrnDesW = 0, jrnDesT = 0, jrnHacW = 0, jrnHacT = 0;
  var progTot = 0, connTot = 0;
  var cells = {}, dateSet = {}, byCoord = {}, byFleet = {};

  function fleetBag(nm) {
    return byFleet[nm] || (byFleet[nm] = { prog: 0, conn: 0, plates: {}, sin: {} });
  }

  function cellOf(k) {
    return cells[k] || (cells[k] = {
      res: 0, losaW: 0, losaT: 0, jrnW: 0, jrnT: 0, pkpW: 0, pkpT: 0,
      whb: 0, prog: 0, conn: 0
    });
  }
  function coordBag(nm) {
    return byCoord[nm] || (byCoord[nm] = {
      losaW: 0, losaT: 0, jrnW: 0, jrnT: 0, pkpW: 0, pkpT: 0,
      res: 0, whb: 0, prog: 0, conn: 0
    });
  }
  function coordsAt(dk, hr) { return shiftMap[dk + '|' + hr] || []; }
  function inScope(dk, hr) {
    if (dk < from || dk > to) return false;
    if (hoursSet && !hoursSet['h' + hr]) return false;
    if (coord) {
      var cs = shiftMap[dk + '|' + hr];
      if (!cs || cs.indexOf(coord) < 0) return false;
    }
    return true;
  }
  function sw(seg, code) { return String(seg).trim().indexOf(code) === 0; }

  /* Coordinadores de turno en el alcance: aparecen aunque no registren eventos. */
  Object.keys(shiftMap).forEach(function (k) {
    var parts = k.split('|');
    if (inScope(parts[0], Number(parts[1]))) {
      shiftMap[k].forEach(function (nm) { coordBag(nm); });
    }
  });

  /* Losa (KPI 2) */
  (function () {
    var t = _tbl(SH.LOSA);
    var seg = _col(t, COL.losaSeg, true), ts = _col(t, COL.losaTs, true);
    for (var r = 0; r < t.n; r++) {
      var s = seg[r]; if (s == null || s === '') continue;
      var d = _toDate(ts[r]); if (!d) continue;
      var dk = _dk(d), hr = d.getHours();
      if (!inScope(dk, hr)) continue;
      dateSet[dk] = true;
      var c = cellOf(dk + '|' + hr);
      var bad = sw(s, '03.') || sw(s, '04.');
      losaT++; c.losaT++;
      if (bad) { losaW++; c.losaW++; }
      coordsAt(dk, hr).forEach(function (nm) {
        var b = coordBag(nm); b.losaT++; if (bad) b.losaW++;
      });
    }
  })();

  /* Journey (KPI 3) — segmentado Total | Desde | Hacia Aeropuerto */
  (function () {
    var t = _tbl(SH.JOURNEY);
    var seg = _col(t, COL.jrnSeg, true), ts = _col(t, COL.jrnTs, true);
    var dir = _col(t, COL.jrnDir, false);
    for (var r = 0; r < t.n; r++) {
      var s = seg[r]; if (s == null || s === '') continue;
      var d = _toDate(ts[r]); if (!d) continue;
      var dk = _dk(d), hr = d.getHours();
      if (!inScope(dk, hr)) continue;
      dateSet[dk] = true;
      var c = cellOf(dk + '|' + hr);
      var bad = sw(s, '04.');   // > 90 min
      jrnT++; c.jrnT++;
      if (bad) { jrnW++; c.jrnW++; }
      if (dir) {
        var dv = String(dir[r] || '').trim();
        if (dv.indexOf('Desde') === 0)      { jrnDesT++; if (bad) jrnDesW++; }
        else if (dv.indexOf('Hacia') === 0) { jrnHacT++; if (bad) jrnHacW++; }
      }
      coordsAt(dk, hr).forEach(function (nm) {
        var b = coordBag(nm); b.jrnT++; if (bad) b.jrnW++;
      });
    }
  })();

  /* Impuntualidad (KPI 4) — SOLO 'Hacia Aeropuerto' (excluye 'Desde Aeropuerto' y 'Otros') */
  (function () {
    var t = _tbl(SH.PICKUP);
    var seg = _col(t, COL.pkpSeg, true), ts = _col(t, COL.pkpTs, true);
    var dir = _col(t, COL.pkpDir, false);
    for (var r = 0; r < t.n; r++) {
      if (dir && String(dir[r] || '').trim().indexOf('Hacia') !== 0) continue;
      var s = seg[r]; if (s == null || s === '') continue;
      var d = _toDate(ts[r]); if (!d) continue;
      var dk = _dk(d), hr = d.getHours();
      if (!inScope(dk, hr)) continue;
      dateSet[dk] = true;
      var c = cellOf(dk + '|' + hr);
      var bad = sw(s, '03.') || sw(s, '04.');
      pkpT++; c.pkpT++;
      if (bad) { pkpW++; c.pkpW++; }
      coordsAt(dk, hr).forEach(function (nm) {
        var b = coordBag(nm); b.pkpT++; if (bad) b.pkpW++;
      });
    }
  })();

  /* Rescates */
  (function () {
    var t = _tbl(SH.RESCATE);
    var ts = _col(t, COL.resTs, true);
    var cl = RESCATE_CLIENT_ID ? _col(t, COL.resClient, false) : null;
    for (var r = 0; r < t.n; r++) {
      if (cl && String(cl[r]).trim() !== RESCATE_CLIENT_ID) continue;
      var d = _toDate(ts[r]); if (!d) continue;
      var dk = _dk(d), hr = d.getHours();
      if (!inScope(dk, hr)) continue;
      dateSet[dk] = true;
      res++; cellOf(dk + '|' + hr).res++;
      coordsAt(dk, hr).forEach(function (nm) { coordBag(nm).res++; });
    }
  })();

  /* Conexiones Efectivas: WH Busy por bloque + set de patentes conectadas (con WH).
     Las filas sin Working Hours son duplicados del export y se excluyen. */
  var conexSet = {}, plateSeen = {};
  (function () {
    var t = _tbl(SH.CONEX);
    var dt = _col(t, COL.conexDate, true), hh = _col(t, COL.conexHour, true);
    var pl = _col(t, COL.conexPlate, true);
    var wb = _col(t, COL.conexWHB, false);
    var wh = _col(t, COL.conexWH, false);
    for (var r = 0; r < t.n; r++) {
      if (wh && (wh[r] === '' || wh[r] == null)) continue;
      var d = _toDate(dt[r]); if (!d) continue;
      var hr = Math.round(Number(hh[r])); if (isNaN(hr)) continue;
      var dk = _dk(d);
      if (!inScope(dk, hr)) continue;
      var plate = _normPlate(pl[r]);
      if (plate) { conexSet[dk + '|' + hr + '|' + plate] = true; plateSeen[plate] = true; }
      var v = wb ? (Number(wb[r]) || 0) : 0;
      whbTot += v;
      cellOf(dk + '|' + hr).whb += v;
      if (v) {
        coordsAt(dk, hr).forEach(function (nm) { coordBag(nm).whb += v; });
      }
    }
  })();

  /* Programación Turnos & Patentes: Disponibilidad Programada y Conectado de lo Programado.
     1 fila = 1 van informada para una franja horaria de una fecha. */
  (function () {
    var t;
    try { t = _tbl(SH.PROG); } catch (e) { return; }
    var dt = _col(t, COL.progDate, true), hh = _col(t, COL.progHour, true);
    var pl = _col(t, COL.progPlate, true);
    var fl = _col(t, COL.progFleet, false);
    var seen = {};
    for (var r = 0; r < t.n; r++) {
      var d = _toDate(dt[r]); if (!d) continue;
      var hr = Math.round(Number(hh[r])); if (isNaN(hr)) continue;
      var dk = _dk(d);
      if (!inScope(dk, hr)) continue;
      var plate = _normPlate(pl[r]); if (!plate) continue;
      var key = dk + '|' + hr + '|' + plate;
      if (seen[key]) continue;
      seen[key] = true;
      dateSet[dk] = true;
      var c = cellOf(dk + '|' + hr);
      progTot++; c.prog++;
      var ok = !!conexSet[key];
      if (ok) { connTot++; c.conn++; }
      coordsAt(dk, hr).forEach(function (nm) {
        var b = coordBag(nm); b.prog++; if (ok) b.conn++;
      });

      /* Cobertura del export de conexiones, por flota */
      var fname = fl ? String(fl[r] || '').trim() : '(sin flota)';
      var f = fleetBag(fname || '(sin flota)');
      f.prog++; if (ok) f.conn++;
      f.plates[plate] = true;
      if (!plateSeen[plate]) f.sin[plate] = true;
    }
  })();

  var dates = Object.keys(dateSet).sort();
  var hours = hoursSel ? hoursSel.slice().sort(function (a, b) { return a - b; }) : _allHours();

  var cellOut = {};
  Object.keys(cells).forEach(function (k) {
    var c = cells[k];
    cellOut[k] = {
      res: c.res,
      losa: c.losaT ? c.losaW / c.losaT : null,
      jrn:  c.jrnT  ? c.jrnW  / c.jrnT  : null,
      pkp:  c.pkpT  ? c.pkpW  / c.pkpT  : null,
      whb:  _round(c.whb, 2),
      prog: c.prog,
      conn: c.conn,
      w:    { losa: c.losaW, jrn: c.jrnW, pkp: c.pkpW },
      n:    { losa: c.losaT, jrn: c.jrnT, pkp: c.pkpT }
    };
  });

  var coordsOut = Object.keys(byCoord).sort().map(function (nm) {
    var b = byCoord[nm];
    return {
      name: nm,
      losa: b.losaT ? b.losaW / b.losaT : null, losaW: b.losaW, losaN: b.losaT,
      jrn:  b.jrnT  ? b.jrnW  / b.jrnT  : null, jrnW:  b.jrnW,  jrnN:  b.jrnT,
      pkp:  b.pkpT  ? b.pkpW  / b.pkpT  : null, pkpW:  b.pkpW,  pkpN:  b.pkpT,
      res:  b.res,
      whb:  _round(b.whb, 1),
      prog: b.prog,
      conn: b.conn
    };
  });

  /* Cobertura: flotas programadas cuyas patentes no aparecen en el export de conexiones.
     Sin esto, una flota ausente del CSV se ve igual que una flota que no se conectó. */
  var coverage = Object.keys(byFleet).sort().map(function (nm) {
    var f = byFleet[nm];
    var np = Object.keys(f.plates).length, ns = Object.keys(f.sin).length;
    return { fleet: nm, prog: f.prog, conn: f.conn, plates: np, sinRegistro: ns };
  }).sort(function (a, b) { return b.prog - a.prog; });

  var ciegas = coverage.filter(function (f) { return f.plates > 0 && f.sinRegistro === f.plates; });
  var parciales = coverage.filter(function (f) { return f.sinRegistro > 0 && f.sinRegistro < f.plates; });

  var dataWarning = '';
  if (ciegas.length) {
    dataWarning = 'El export "WH Busy By Patente" no trae ningún registro para ' +
      ciegas.map(function (f) { return f.fleet; }).join(', ') +
      '. Esas vans programadas se cuentan como "no conectadas" aunque hayan trabajado, ' +
      'así que la tasa de conexión está subestimada.';
  } else if (parciales.length) {
    var faltan = 0;
    parciales.forEach(function (f) { faltan += f.sinRegistro; });
    dataWarning = faltan + ' patentes programadas no aparecen en el export de conexiones. ' +
      'Revisa el filtro del CSV "WH Busy By Patente" antes de tomar la tasa de conexión como definitiva.';
  }

  return {
    cards: {
      losa: losaT ? losaW / losaT : null, losaW: losaW, losaN: losaT,
      jrn:  jrnT  ? jrnW  / jrnT  : null, jrnW:  jrnW,  jrnN:  jrnT,
      jrnDes: jrnDesT ? jrnDesW / jrnDesT : null, jrnDesW: jrnDesW, jrnDesN: jrnDesT,
      jrnHac: jrnHacT ? jrnHacW / jrnHacT : null, jrnHacW: jrnHacW, jrnHacN: jrnHacT,
      pkp:  pkpT  ? pkpW  / pkpT  : null, pkpW:  pkpW,  pkpN:  pkpT,
      res:  res,
      whb:  _round(whbTot, 1),
      prog: progTot,
      conn: connTot,
      noconn: progTot - connTot,
      connRate: progTot ? connTot / progTot : null
    },
    byCoord: coordsOut,
    coverage: coverage,
    heatmap: { dates: dates, hours: hours, cells: cellOut },
    filters: { from: from, to: to, coord: coord || 'Todos' },
    shiftWarning: shift.error || '',
    dataWarning: dataWarning
  };
}

/* ------------------------------------------------------------------ API: detalle de celda
   Lectura POR BANDA: se ubica el tramo de filas del bloque con las columnas de fecha/hora y
   solo entonces se leen las demás columnas de ese tramo. */
function getCellDetail(dk, hr, coordinator) {
  hr = Number(hr);
  var cache = CacheService.getScriptCache();
  var key = _ckey('det3_', [dk, hr, coordinator || '', _fingerprint(false)]);
  var hit = _cacheGetJson(cache, key);
  if (hit) return hit;

  var coord = (coordinator && coordinator !== '__ALL__') ? coordinator : null;
  var coords = _shift(false).map[dk + '|' + hr] || [];
  var blockOk = !coord || coords.indexOf(coord) >= 0;

  /* --- Rescates --- */
  var rescates = (function () {
    var cols = ['Start At Local Dttm', 'Product Name', 'Start Neighborhood',
                'Dirección de inicio', 'Canal de DO', 'Company Id', 'Journey Id', 'End State'];
    var out = { rows: [], cols: cols };
    if (!blockOk) return out;

    var t = _tbl(SH.RESCATE);
    var band = _band(t, dk, hr, { ts: COL.resTs });
    if (!band) return out;

    var ts = _colBand(t, COL.resTs, band.start, band.count);
    var cl = RESCATE_CLIENT_ID ? _colBand(t, COL.resClient, band.start, band.count) : null;
    var colData = cols.map(function (c) { return _colBand(t, c, band.start, band.count); });

    for (var i = 0; i < band.count; i++) {
      if (cl && String(cl[i]).trim() !== RESCATE_CLIENT_ID) continue;
      var d = _toDate(ts[i]); if (!d) continue;
      if (_dk(d) !== dk || d.getHours() !== hr) continue;
      var row = {};
      cols.forEach(function (c, j) {
        var val = colData[j] ? colData[j][i] : '';
        if (val instanceof Date) {
          val = _dk(val) + ' ' + _p2(val.getHours()) + ':' + _p2(val.getMinutes()) + ':' + _p2(val.getSeconds());
        }
        row[c] = (val == null ? '' : val);
      });
      out.rows.push(row);
    }
    return out;
  })();

  /* --- Conexiones Efectivas (todos los productos; el producto sale del sufijo de la patente) --- */
  var plateSet = {};
  var conex = (function () {
    var cols = ['Patente', 'Producto', 'Flota', 'Driver Name', 'Tariff Name',
                'Working Hours', 'Working Hours Busy'];
    var sum = { N: _bag(), C: _bag(), X: _bag() };
    function pack(b) { return { wh: _round(b.wh, 2), whb: _round(b.whb, 2), vans: Object.keys(b.vans).length }; }
    var out = {
      rows: [], cols: cols,
      summary: { N: pack(sum.N), C: pack(sum.C), X: pack(sum.X) },
      totals: { wh: 0, whb: 0, vans: 0 }
    };
    if (!blockOk) return out;

    var t = _tbl(SH.CONEX);
    var band = _band(t, dk, hr, { date: COL.conexDate, hour: COL.conexHour });
    if (!band) return out;

    var dt = _colBand(t, COL.conexDate, band.start, band.count);
    var hh = _colBand(t, COL.conexHour, band.start, band.count);
    var pl = _colBand(t, COL.conexPlate, band.start, band.count);
    var co = _colBand(t, COL.conexCompany, band.start, band.count) ||
             _colBand(t, COL.conexCompanyFb, band.start, band.count);
    var dr = _colBand(t, COL.conexDriver, band.start, band.count);
    var tf = _colBand(t, COL.conexTariff, band.start, band.count);
    var wh = _colBand(t, COL.conexWH, band.start, band.count);
    var wb = _colBand(t, COL.conexWHB, band.start, band.count);

    var whSum = 0, whbSum = 0, vanSet = {};

    for (var i = 0; i < band.count; i++) {
      if (wh && (wh[i] === '' || wh[i] == null)) continue;   // duplicados sin WH
      var d = _toDate(dt[i]); if (!d) continue;
      if (_dk(d) !== dk) continue;
      if (Math.round(Number(hh[i])) !== hr) continue;

      var raw = String(pl[i] || '').trim(); if (!raw) continue;
      var norm = _normPlate(raw);
      plateSet[norm] = true;
      vanSet[norm] = true;

      var prod = _prodOf(raw);
      var whV  = wh ? (Number(wh[i]) || 0) : 0;
      var whbV = wb ? (Number(wb[i]) || 0) : 0;

      whSum += whV; whbSum += whbV;

      out.rows.push({
        'Patente': norm,
        'Producto': prod,
        'Flota': co ? String(co[i] || '').trim() : '',
        'Driver Name': dr ? String(dr[i] || '') : '',
        'Tariff Name': tf ? String(tf[i] || '') : '',
        'Working Hours': _round(whV, 3),
        'Working Hours Busy': _round(whbV, 3)
      });

      var b = sum[prod] || sum.X;
      b.wh += whV; b.whb += whbV; b.vans[norm] = true;
    }

    out.summary = { N: pack(sum.N), C: pack(sum.C), X: pack(sum.X) };
    out.totals = { wh: _round(whSum, 2), whb: _round(whbSum, 2), vans: Object.keys(vanSet).length };
    return out;
  })();

  /* --- Programación del bloque: vans programadas y su estado --- */
  var prog = (function () {
    var out = {
      rows: [], cols: ['Patente', 'Flota', 'Bloque Asignado', 'Estado'],
      summary: { prog: 0, conn: 0, noconn: 0 }
    };
    if (!blockOk) return out;

    var t;
    try { t = _tbl(SH.PROG); } catch (e) { return out; }
    var band = _band(t, dk, hr, { date: COL.progDate, hour: COL.progHour });
    if (!band) return out;

    var dt = _colBand(t, COL.progDate, band.start, band.count);
    var hh = _colBand(t, COL.progHour, band.start, band.count);
    var pl = _colBand(t, COL.progPlate, band.start, band.count);
    var fl = _colBand(t, COL.progFleet, band.start, band.count);
    var bl = _colBand(t, COL.progBloque, band.start, band.count);

    var seen = {};
    for (var i = 0; i < band.count; i++) {
      var d = _toDate(dt[i]); if (!d) continue;
      if (_dk(d) !== dk) continue;
      if (Math.round(Number(hh[i])) !== hr) continue;
      var plate = _normPlate(pl[i]); if (!plate || seen[plate]) continue;
      seen[plate] = true;
      out.rows.push({
        'Patente': plate,
        'Flota': fl ? String(fl[i] || '').trim() : '',
        'Bloque Asignado': bl ? String(bl[i] || '') : '',
        'Estado': plateSet[plate] ? 'Conectada' : 'No se conectó'
      });
    }

    out.rows.sort(function (a, b) {
      if (a.Estado !== b.Estado) return a.Estado === 'No se conectó' ? -1 : 1;
      return a.Patente < b.Patente ? -1 : 1;
    });

    var conn = 0;
    out.rows.forEach(function (r) { if (r.Estado === 'Conectada') conn++; });
    out.summary = { prog: out.rows.length, conn: conn, noconn: out.rows.length - conn };
    return out;
  })();

  var result = { dk: dk, hr: hr, coords: coords, rescates: rescates, conex: conex, prog: prog };
  _cachePutJson(cache, key, result, CACHE_TTL_SEC);
  return result;
}

/* ------------------------------------------------------------------ Diagnóstico */
function diagnostico() {
  var b = _monthBounds();
  Logger.log('📅 Rango seleccionable: ' + b.min + ' → ' + b.max + ' | por defecto desde ' + b.defFrom);

  var s = _shift(true);
  Logger.log('👥 Coordinadores: ' + (s.coords.join(', ') || '(ninguno)'));
  Logger.log('🕐 Bloques con coordinador de turno (sin franjas administrativas): ' +
    Object.keys(s.map).length);
  if (s.error) Logger.log('⚠️ ' + s.error);

  [SH.LOSA, SH.JOURNEY, SH.PICKUP, SH.RESCATE, SH.PROG, SH.CONEX].forEach(function (n) {
    try {
      var sh = _sheet(n);
      Logger.log('📄 ' + sh.getName() + ': ' + (sh.getLastRow() - 1) + ' filas');
    } catch (e) {
      Logger.log('❌ ' + (Array.isArray(n) ? n[0] : n) + ': ' + e.message);
    }
  });
}

/* util */
function _bag() { return { wh: 0, whb: 0, vans: {} }; }
function _allHours() { var a = []; for (var i = 0; i < 24; i++) a.push(i); return a; }
function _round(x, d) { var f = Math.pow(10, d || 0); return Math.round((Number(x) || 0) * f) / f; }
