import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';

const accepted = '.pdf,.x83,.d83,.d84,.d86,.xlsx';
const formats = ['PDF', 'X83', 'D83', 'D84', 'D86', 'XLSX'];

function FileField({id, file, setFile, primary = false}) {
  const [dragging, setDragging] = useState(false);
  function drop(event) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length) setFile(event.dataTransfer.files[0]);
  }
  return <div className="bg-field">
    <div className="bg-field-label"><strong>{primary ? 'Leistungsverzeichnis' : 'Ergänzende Anlage'}</strong>
      {!primary && <span>Optional</span>}</div>
    <label className={`bg-drop ${primary ? 'bg-drop-primary' : ''} ${dragging ? 'is-dragging' : ''}`}
      onDragOver={event => {event.preventDefault(); setDragging(true);}}
      onDragLeave={() => setDragging(false)} onDrop={drop}>
      <input id={id} type="file" accept={primary ? accepted : '.docx'}
        aria-label={primary ? 'Leistungsverzeichnis' : 'DOCX-Anlage'}
        onChange={event => setFile(event.target.files[0])}/>
      <span className="bg-file-icon" aria-hidden="true">{primary ? '↑' : '+'}</span>
      <span className="bg-file-label"><strong>{file ? file.name : primary ? 'Datei auswählen oder ablegen' : 'DOCX-Anlage auswählen'}</strong>
        <small>{file ? `${new Intl.NumberFormat('de-DE', {maximumFractionDigits: 1}).format(file.size / 1024)} KB · Datei austauschen`
          : primary ? 'PDF, GAEB oder XLSX · bis 32 MB' : 'Ergänzende Angaben zur Prüfung hinzufügen'}</small>
      </span>
    </label>
  </div>;
}

function Upload({model, history}) {
  const [file, setFile] = useState();
  const [attachment, setAttachment] = useState();
  const [useModel, setUseModel] = useState(false);
  const [coverage, setCoverage] = useState('full');
  const [trade, setTrade] = useState('');
  const [job, setJob] = useState(null);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState(null);
  const suffix = file?.name.split('.').at(-1).toLowerCase();
  const useAI = Boolean(model && suffix === 'pdf' && useModel);

  useEffect(() => {
    if (!job) return;
    const tick = setInterval(() => setSeconds(Math.floor((Date.now() - job.started) / 1000)), 1000);
    return () => clearInterval(tick);
  }, [job]);

  async function submit(event) {
    event.preventDefault();
    if (!file || job) return;
    setError(null);
    if (!formats.includes(suffix?.toUpperCase()) || (attachment && !/\.docx$/i.test(attachment.name))) {
      setError({message: 'Bitte ein unterstütztes LV und gegebenenfalls eine DOCX-Anlage auswählen.'});
      return;
    }
    if ([file, attachment].some(value => value?.size > 32 * 1024 * 1024)) {
      setError({message: 'Dateien dürfen jeweils höchstens 32 MB groß sein.'});
      return;
    }
    const started = Date.now();
    setSeconds(0);
    setJob({started, label: useAI ? 'Datei und lokales Modell werden geprüft' : 'Datei wird geprüft'});
    let review;
    try {
      const query = new URLSearchParams({name: file.name});
      if (trade.trim()) query.set('trade', trade.trim());
      if (useAI) {
        query.set('semantic', '1');
        query.set('coverage', coverage);
      }
      const types = {pdf: 'application/pdf', x83: 'application/xml'};
      const response = await fetch('/upload?' + query, {
        method: 'POST', body: file, headers: {'Content-Type': types[suffix] || 'application/octet-stream'},
      });
      if (!response.ok) throw new Error(await response.text());
      review = response.url;
      if (attachment) {
        setJob({started, label: 'DOCX-Anlage wird geprüft'});
        const added = await fetch(review + '/attachment?' + new URLSearchParams({name: attachment.name}), {
          method: 'POST', body: attachment, headers: {'Content-Type': 'application/octet-stream'},
        });
        if (!added.ok) throw new Error(await added.text());
      }
      location.assign(review);
    } catch (err) {
      setError({message: err.message || 'Unbekannter Fehler.', review});
      setJob(null);
    }
  }

  return <div className="bg-upload-layout">
    <section className="bg-intro" aria-labelledby="bg-headline">
      <div className="bg-brandline"><span className="bg-mark" aria-hidden="true">B</span> BIDGUARD AI</div>
      <h1 id="bg-headline">Ausschreibung prüfen</h1>
      <p>Finden Sie Widersprüche, offene Anforderungen und Rechenabweichungen mit Belegen aus Ihrer Ausschreibung.</p>
      <ul className="bg-formats" aria-label="Unterstützte Formate">{formats.map(format => <li key={format}>{format}</li>)}</ul>
      <div className="bg-workflow">
        <div><span aria-hidden="true">01</span><strong>LV hochladen</strong><small>Optional mit DOCX-Anlage</small></div>
        <div><span aria-hidden="true">02</span><strong>Befunde prüfen</strong><small>Mit Originalzitaten und Fundstellen</small></div>
        <div><span aria-hidden="true">03</span><strong>Bericht exportieren</strong><small>Mit Ihren Bieterfragen</small></div>
      </div>
    </section>
    <section className="bg-card" aria-labelledby="bg-upload-title">
      <h2 id="bg-upload-title">Neue Prüfung</h2>
      <form id="upload" onSubmit={submit}>
        <fieldset disabled={Boolean(job)} className="bg-upload-fields">
          <FileField id="lv" file={file} setFile={setFile} primary/>
          <FileField id="attachment" file={attachment} setFile={setAttachment}/>
          {suffix === 'xlsx' && <p className="bg-help">XLSX-Kopfzeile: OZ, Kurztext, Menge, ME.</p>}
          {model && <div className="bg-model">
            <label className="bg-toggle"><input type="checkbox" id="semantic" checked={useAI}
              disabled={suffix !== 'pdf'} onChange={event => setUseModel(event.target.checked)}/>
              <span><strong>Lokales Modell für PDF verwenden</strong><small>{model}</small></span>
            </label>
            {useAI && <div className="bg-coverage">
              <label htmlFor="coverage">Umfang der Modellprüfung</label>
              <select id="coverage" value={coverage} onChange={event => setCoverage(event.target.value)}>
                <option value="full">Alle Textabschnitte</option><option value="quick">Stichprobe (schnell)</option>
              </select>
              <small>Lange PDFs können deutlich mehr Zeit benötigen.</small>
            </div>}
          </div>}
          {history && <details className="bg-options"><summary>Historische Regeln filtern</summary>
            <label htmlFor="history-trade">Gewerk (optional)</label>
            <input id="history-trade" maxLength={120} value={trade} onChange={event => setTrade(event.target.value)}/>
          </details>}
        </fieldset>
        <button className="bg-submit" type="submit" disabled={!file || Boolean(job)}>
          {job ? 'Prüfung läuft …' : 'Datei prüfen'} <span aria-hidden="true">→</span>
        </button>
        {job && <div id="progress" className="bg-notice" role="status">
          <strong>{job.label}</strong><small>{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')} vergangen · Tab geöffnet lassen</small>
        </div>}
        {error && <div className="bg-notice bg-error" role="status">
          <strong>Prüfung fehlgeschlagen.</strong><small>{error.message}</small>
          {error.review && <a href={error.review}>LV-Prüfung öffnen</a>}
        </div>}
      </form>
    </section>
  </div>;
}

function ReviewToolbar({findings}) {
  const [filter, setFilter] = useState('all');
  const [statuses, setStatuses] = useState(() => Object.fromEntries(findings.map(f => [f.id, f.status])));
  const filters = [['all', 'Alle Befunde'], ['open', 'Offen'], ['confirmed', 'Bestätigt'], ['dismissed', 'Verworfen']];
  const visible = findings.filter(f => filter === 'all' || statuses[f.id] === filter);
  useEffect(() => {
    const sync = event => {
      const input = event.target;
      if (input.id?.startsWith('status-')) {
        setStatuses(previous => ({...previous, [input.id.slice(7)]: input.value}));
      }
    };
    document.addEventListener('change', sync);
    return () => document.removeEventListener('change', sync);
  }, []);
  useEffect(() => {
    const ids = new Set(visible.map(f => f.id));
    findings.forEach(({id}) => {
      const card = document.getElementById(id);
      if (card) card.hidden = !ids.has(id);
    });
  }, [visible, findings]);
  if (!findings.length) return null;
  return <section className="bg-toolbar" aria-label="Befunde filtern">
    <div><strong>{findings.length} {findings.length === 1 ? 'Befund' : 'Befunde'}</strong>
      <span>{visible.length} angezeigt</span></div>
    <div className="bg-filters">{filters.map(([key, label]) =>
      <button type="button" key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>
        {label} <span>{key === 'all' ? findings.length : findings.filter(f => statuses[f.id] === key).length}</span>
      </button>)}</div>
    {!visible.length && <p role="status">Keine Befunde mit diesem Status.</p>}
  </section>;
}

const mount = document.querySelector('[data-react-workspace]');
if (mount) {
  const props = JSON.parse(mount.dataset.props);
  if (mount.dataset.reactWorkspace === 'upload') {
    document.querySelector('main').classList.add('bg-home');
    createRoot(mount).render(<Upload {...props}/>);
  } else {
    document.querySelector('main').classList.add('bg-review');
    createRoot(mount).render(<ReviewToolbar {...props}/>);
  }
}
