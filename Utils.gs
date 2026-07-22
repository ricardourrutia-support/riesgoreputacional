/**
 * BSC Aeropuerto — Utilidades
 */

// ─── Helpers de Hojas ───
function getSheet_(nombre) { return SpreadsheetApp.getActiveSpreadsheet().getSheetByName(nombre); }

function getAllData_(nombre) {
  var hoja = getSheet_(nombre);
  if (!hoja || hoja.getLastRow() < 2) return [];
  var data = hoja.getRange(2,1,hoja.getLastRow()-1,hoja.getLastColumn()).getValues();
  var headers = hoja.getRange(1,1,1,hoja.getLastColumn()).getValues()[0];
  return data.map(function(row) {
    var obj = {}; headers.forEach(function(h,i) { obj[h] = row[i]; }); return obj;
  });
}

function getNextId_(nombre) {
  var hoja = getSheet_(nombre);
  if (hoja.getLastRow() < 2) return 1;
  var ids = hoja.getRange(2,1,hoja.getLastRow()-1,1).getValues().map(function(r){return r[0]||0});
  return Math.max.apply(null,ids)+1;
}

function appendRow_(nombre, rowData) { getSheet_(nombre).appendRow(rowData); }

function findRowIndex_(nombre, colIndex, valor) {
  var hoja = getSheet_(nombre);
  if (hoja.getLastRow() < 2) return -1;
  var col = hoja.getRange(2,colIndex,hoja.getLastRow()-1,1).getValues();
  for (var i=0; i<col.length; i++) { if (String(col[i][0])===String(valor)) return i+2; }
  return -1;
}

function getConfig_(clave) {
  var hoja = getSheet_('Config');
  if (!hoja || hoja.getLastRow() < 2) return null;
  var data = hoja.getRange(2,1,hoja.getLastRow()-1,2).getValues();
  for (var i=0; i<data.length; i++) { if (data[i][0]===clave) return data[i][1]; }
  return null;
}

// ─── Normalización de texto ───
function limpiarTexto_(texto) {
  if (!texto) return '';
  return String(texto).trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ');
}

function nombreCompletoBuk_(nombre, pApellido, sApellido) {
  return [nombre||'',pApellido||'',sApellido||''].filter(function(p){return p.trim()}).join(' ').toUpperCase();
}

// ─── Matching de nombres ───
function scoreMatching_(nombreBukNorm, nombre360Norm) {
  var tBuk = nombreBukNorm.split(' ').filter(function(t){return t});
  var t360 = nombre360Norm.split(' ').filter(function(t){return t});
  if (!t360.length || !tBuk.length) return 0;
  var matches = 0;
  t360.forEach(function(t) {
    if (tBuk.indexOf(t) >= 0) matches += 1;
    else if (t.length >= 3) {
      for (var i=0; i<tBuk.length; i++) { if (tBuk[i].indexOf(t)===0) { matches += 0.85; break; } }
    }
  });
  return matches / t360.length;
}

// ─── normHora_ — CENTRAL, usado por Consolidacion, Writeback y Analytics ───
function normHora_(v) {
  if (!v || v === '' || v === '-') return '';
  if (v instanceof Date) {
    var h = v.getHours(), m = v.getMinutes();
    return (h<10?'0':'')+h+':'+(m<10?'0':'')+m;
  }
  var s = String(v).trim();
  if (s===''||s==='-'||s==='None'||s==='undefined') return '';
  var num = parseFloat(s);
  if (!isNaN(num) && num >= 0 && num < 1) {
    var tot = Math.round(num*86400);
    var hh = Math.floor(tot/3600), mm = Math.floor((tot%3600)/60);
    return (hh<10?'0':'')+hh+':'+(mm<10?'0':'')+mm;
  }
  var match = s.match(/(\d{1,2}):(\d{2})/);
  if (match) {
    var hh = parseInt(match[1],10), mm = parseInt(match[2],10);
    return (hh<10?'0':'')+hh+':'+(mm<10?'0':'')+mm;
  }
  return '';
}

// ─── Parsing de horarios ───
var RE_RANGO = /(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–aA]\s*(\d{1,2}:\d{2}(?::\d{2})?)/;
var LIBRES = {'libre':1,'descanso':1,'desc':1,'d':1,'l':1,'':1};
var RUIDO_PATTERNS = [/^t\d+$/i,/^noche$/i,/^reunion/i,/^enviar /i,/^obs:/i,/^este cuadro/i,/^ok$/i,/^\.$/,/^ejecutivo/i,/^anfitr/i,/^coordinador/i,/^supervisor/i,/^sabado/i,/^domingo/i,/^lunes|^martes|^miercoles|^jueves|^viernes/i,/^\d+\.\d+$/,/^\d{4}-\d{2}-\d{2}/,/^quiere /i,/^tres dias/i,/^dos domingos/i,/^domingos libres/i];

function esRuido_(v) { var s=limpiarTexto_(v); return RUIDO_PATTERNS.some(function(rx){return rx.test(s)}); }
function esLibre_(v) { return limpiarTexto_(v) in LIBRES; }

function normalizarHora_(horaStr) {
  var p = String(horaStr).split(':');
  var h = parseInt(p[0],10), m = parseInt(p[1]||'0',10);
  return (h<10?'0':'')+h+':'+(m<10?'0':'')+m;
}

function cruzaMedianoche_(hi, hf) { return horaAMinutos_(hf) <= horaAMinutos_(hi); }
function horaAMinutos_(horaStr) { var p=String(horaStr).split(':'); return parseInt(p[0],10)*60+parseInt(p[1]||'0',10); }

function minutosEntre_(horaPlan, horaReal) {
  var plan=horaAMinutos_(horaPlan), real=horaAMinutos_(horaReal);
  var diff=real-plan;
  if (diff>720) diff-=1440; else if (diff<-720) diff+=1440;
  return diff;
}

function extraerRangoHorario_(texto) {
  if (!texto) return null;
  var s = String(texto).trim();
  if (!s || esRuido_(s)) return null;
  if (esLibre_(s)) return {hora_inicio:null,hora_fin:null,cruza_medianoche:false,es_libre:true,texto_original:s};
  var m = RE_RANGO.exec(s);
  if (!m) return null;
  var hi=normalizarHora_(m[1]), hf=normalizarHora_(m[2]);
  return {hora_inicio:hi,hora_fin:hf,cruza_medianoche:cruzaMedianoche_(hi,hf),es_libre:false,texto_original:s};
}

// ─── Parsing de fechas ───
function parseFechaDmy_(texto) {
  if (!texto) return null;
  if (texto instanceof Date) return Utilities.formatDate(texto,Session.getScriptTimeZone(),'yyyy-MM-dd');
  var s = String(texto).trim();
  if (!s||s==='-'||s==='None') return null;
  var m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) { var d=parseInt(m[1],10),mo=parseInt(m[2],10),y=parseInt(m[3],10); return y+'-'+(mo<10?'0':'')+mo+'-'+(d<10?'0':'')+d; }
  m = s.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (m) { var d=parseInt(m[1],10),mo=parseInt(m[2],10),y=parseInt(m[3],10); return y+'-'+(mo<10?'0':'')+mo+'-'+(d<10?'0':'')+d; }
  m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return m[0];
  return null;
}

function parseFechaExcel_(valor) {
  if (!valor) return null;
  if (valor instanceof Date) return Utilities.formatDate(valor,Session.getScriptTimeZone(),'yyyy-MM-dd');
  return parseFechaDmy_(String(valor));
}

// ─── Hash ───
function calcularHash_() {
  var args = Array.prototype.slice.call(arguments);
  var contenido = args.map(function(c){return c!=null?String(c):''}).join('|');
  var raw = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,contenido);
  return raw.slice(0,8).map(function(b){return('0'+(b<0?b+256:b).toString(16)).slice(-2)}).join('');
}

// ─── Roles ───
var ESPECIALIDAD_A_ROL = {'anfitrion':'ANFITRION','ejecutivo':'EJECUTIVO','coordinador':'COORDINADOR','supervisor':'SUPERVISOR'};
function especialidadARol_(esp) {
  if (!esp) return 'ANFITRION';
  var lower = String(esp).toLowerCase();
  for (var clave in ESPECIALIDAD_A_ROL) { if (lower.indexOf(clave) >= 0) return ESPECIALIDAD_A_ROL[clave]; }
  return 'ANFITRION';
}

var MOTIVO_MAP = {'L':'LICENCIA_MEDICA','P':'PERMISO','V':'VACACIONES','D':'DESCANSO','-':'INASISTENCIA_INJUSTIFICADA'};
