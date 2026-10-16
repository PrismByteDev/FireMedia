'use strict';
const $ = id => document.getElementById(id);
const media = $('media');
const readStore = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
const preferences = readStore('firemedia.preferences', {});
const restoredQueue = readStore('firemedia.queue', []);
let libraryReady = false;
let library = [], queue = [], current = null, playlists = readStore('firemedia.playlists', []), selectedPlaylist = null;
let view = 'stage', shuffle = false, repeat = false, audioContext, analyser, filters = [], bins, activeURL, subtitles = [], dragging;
let preset = preferences.preset || 'fireworks', ldmMode = preferences.ldm || 'auto', lowDetail = false, powerSaver = false, batteryLow = false;
let frameId = null, lastTime = 0, simulationTime = 0, paletteIndex = 0, toastTimer, dialogAction = 'empty';
const springs = Array.from({ length: 64 }, () => ({ y: 0, v: 0 }));
const sparks = [];
const frequencies = [60, 170, 350, 1000, 3500, 10000];
const palettes = [[88,164,205,267,325], [13,33,52,340,290], [155,175,196,221,253]];
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const connection = navigator.connection;
function persist() { localStorage.setItem('firemedia.playlists', JSON.stringify(playlists)); }
function savePreferences() { localStorage.setItem('firemedia.preferences', JSON.stringify({ preset, ldm: ldmMode, physics: $('physics').checked, tension: $('tension').value, particles: $('particles').value })); }
function toast(message) { $('toast').textContent = message; $('toast').classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').classList.remove('show'), 3500); }
function time(seconds) { return Number.isFinite(seconds) ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}` : '0:00'; }
function textNode(tag, content, className) { const node = document.createElement(tag); node.textContent = content; if (className) node.className = className; return node; }
const dbPromise = new Promise((resolve, reject) => { const request = indexedDB.open('FireMedia', 1); request.onupgradeneeded = () => request.result.createObjectStore('media', { keyPath: 'id' }); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); });
async function storeFile(track) { const db = await dbPromise; return new Promise((resolve, reject) => { const tx = db.transaction('media', 'readwrite'); tx.objectStore('media').put(track); tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); }); }
async function restoreLibrary() { try { const db = await dbPromise; const request = db.transaction('media').objectStore('media').getAll(); request.onsuccess = () => { libraryReady = true; library = request.result; queue = restoredQueue.filter(id => library.some(t => t.id === id)); render(); }; } catch { toast('Persistent media storage unavailable. Files work for this session.'); } }
async function importFiles(files) {
 const accepted = [...files].filter(f => /^(audio|video)\//.test(f.type) || /\.(mp3|wav|flac|ogg|opus|m4a|aac|mp4|webm|mkv|mov)$/i.test(f.name));
 if (!accepted.length) return toast('Choose audio or video files.');
 let storageFailure = false;
 for (const file of accepted) {
  const id = `${file.name}:${file.size}:${file.lastModified}`;
  let track = library.find(t => t.id === id);
  if (!track) { track = { id, name: file.name.replace(/\.[^.]+$/, ''), filename: file.name, type: file.type, file, favorite: false, lastPlayed: 0 }; library.push(track); try { await storeFile(track); } catch { storageFailure = true; } }
  queue.push(id);
 }
 render(); toast(storageFailure ? 'Added to queue. Storage full or unavailable; some files are session-only.' : `Added ${accepted.length} ${accepted.length === 1 ? 'file' : 'files'} to your queue`);
 if (!current) await playTrack(queue[queue.length - accepted.length]);
 $('fileInput').value = '';
}
function renderTrack(track, inQueue, index) {
 const row = textNode('div', '', `track${track.id === current ? ' current' : ''}`); row.tabIndex = 0; row.setAttribute('role', 'button'); row.setAttribute('aria-label', `Play ${track.name}`);
 row.append(textNode('div', track.id === current && !media.paused ? '▥' : /video|\.(mp4|webm|mkv|mov)$/i.test(track.type + track.filename) ? '▷' : '♫', 'mini-cover'));
 const info = textNode('div', '', 'track-text'); info.append(textNode('strong', track.name), textNode('small', `${track.favorite ? '♥ · ' : ''}${track.filename.split('.').pop().toUpperCase()} · Local file`)); row.append(info);
 row.onclick = () => playTrack(track.id); row.onkeydown = event => { if (event.target === row && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); playTrack(track.id); } };
 if (inQueue) {
  row.draggable = true; row.ondragstart = () => { dragging = index; }; row.ondragover = event => event.preventDefault(); row.ondrop = event => { event.preventDefault(); if (Number.isInteger(dragging)) { const [id] = queue.splice(dragging, 1); queue.splice(index, 0, id); dragging = null; render(); } };
  const up = textNode('button', '↑', 'remove'); up.title = 'Move up'; up.setAttribute('aria-label', `Move ${track.name} up`); up.disabled = index === 0; up.onclick = event => { event.stopPropagation(); [queue[index-1], queue[index]] = [queue[index], queue[index-1]]; render(); }; row.append(up);
  const remove = textNode('button', '×', 'remove'); remove.title = 'Remove from queue'; remove.setAttribute('aria-label', `Remove ${track.name}`); remove.onclick = event => { event.stopPropagation(); queue.splice(index, 1); render(); }; row.append(remove);
 } else if (selectedPlaylist) {
  const remove = textNode('button', '×', 'remove'); remove.title = 'Remove from playlist'; remove.onclick = event => { event.stopPropagation(); const p = playlists.find(p => p.id === selectedPlaylist); p.tracks = p.tracks.filter(id => id !== track.id); persist(); render(); }; row.append(remove);
 } else {
  const add = textNode('button', '+', 'remove'); add.title = 'Add to queue'; add.onclick = event => { event.stopPropagation(); queue.push(track.id); render(); toast('Added to queue'); }; row.append(add);
 }
 return row;
}
function render() {
 if (libraryReady) localStorage.setItem('firemedia.queue', JSON.stringify(queue));
 $('queueCount').textContent = queue.length; $('queueSummary').textContent = `${queue.length} ${queue.length === 1 ? 'track' : 'tracks'}`;
 $('queueTracks').replaceChildren(...queue.map((id, i) => library.find(t => t.id === id) ? renderTrack(library.find(t => t.id === id), true, i) : null).filter(Boolean));
 if (!queue.length) { const empty = textNode('div', '', 'empty'); empty.append(textNode('b', 'Room for a little noise.'), document.createTextNode('Drop your music or videos here.\nYour next soundtrack starts with a file.')); $('queueTracks').append(empty); }
 $('playlists').replaceChildren();
 if (!playlists.length) $('playlists').append(textNode('div', 'Create your first mix ↗', 'playlist-link'));
 playlists.forEach(p => { const button = textNode('button', '', 'playlist-link'); button.append(textNode('span', '☷'), textNode('span', p.name)); button.onclick = () => showView('playlist', p.id); $('playlists').append(button); });
 renderLibrary();
 const track = library.find(t => t.id === current); $('favorite').textContent = track?.favorite ? '♥' : '♡';
}
function renderLibrary() {
 let tracks = [...library];
 if (view === 'recent') tracks = tracks.filter(t => t.lastPlayed).sort((a,b) => b.lastPlayed-a.lastPlayed);
 if (selectedPlaylist) tracks = (playlists.find(p => p.id === selectedPlaylist)?.tracks || []).map(id => library.find(t => t.id === id)).filter(Boolean);
 const query = $('search').value.toLowerCase(); tracks = tracks.filter(t => t.name.toLowerCase().includes(query));
 $('libraryTracks').replaceChildren(...tracks.map(t => renderTrack(t, false)));
 if (!tracks.length) $('libraryTracks').append(textNode('div', query ? 'No matching files.' : 'Your collection starts here. Open local media to add it to your library.', 'empty'));
 if (selectedPlaylist) {
  const actions = textNode('div', '', 'playlist-actions');
  const addQueue = textNode('button', '＋ Add current queue', 'button'); addQueue.onclick = () => { const p = playlists.find(p => p.id === selectedPlaylist); p.tracks.push(...queue); persist(); render(); toast(queue.length ? 'Queue added to playlist' : 'Add files to the queue first'); };
  const rename = textNode('button', 'Rename', 'button'); rename.onclick = () => openPlaylistDialog('rename');
  const remove = textNode('button', 'Delete playlist', 'button'); remove.onclick = () => { playlists = playlists.filter(p => p.id !== selectedPlaylist); persist(); selectedPlaylist = null; showView('library'); render(); toast('Playlist deleted · media files kept'); };
  actions.append(addQueue, rename, remove); $('libraryTracks').prepend(actions);
 }
 if (selectedPlaylist && tracks.length) { const button = textNode('button', '＋ Add playlist to queue', 'button'); button.onclick = () => { queue.push(...tracks.map(t => t.id)); render(); toast('Playlist added to queue'); }; $('libraryTracks').prepend(button); }
}
function showView(next, playlist = null) {
 view = next; selectedPlaylist = playlist; $('stageView').hidden = view !== 'stage'; $('libraryView').hidden = view === 'stage';
 const title = playlist ? playlists.find(p => p.id === playlist)?.name : view === 'recent' ? 'Recently played' : view === 'library' ? 'Media library' : 'Now playing';
 $('pageName').textContent = title; $('heading').textContent = view === 'stage' ? 'Feel every frequency.' : title; $('libraryTitle').textContent = title;
 document.querySelectorAll('.nav').forEach(n => n.classList.toggle('active', n.dataset.view === next)); renderLibrary(); restartVisualization();
}
function setupAudio() {
 if (audioContext) return;
 audioContext = new AudioContext(); const source = audioContext.createMediaElementSource(media); let previous = source;
 filters = frequencies.map(frequency => { const filter = audioContext.createBiquadFilter(); filter.type = 'peaking'; filter.frequency.value = frequency; filter.Q.value = 1; previous.connect(filter); previous = filter; return filter; });
 document.querySelectorAll('.eq input').forEach((input, i) => filters[i].gain.value = +input.value);
 analyser = audioContext.createAnalyser(); analyser.fftSize = 2048; analyser.smoothingTimeConstant = .72; previous.connect(analyser); analyser.connect(audioContext.destination); bins = new Uint8Array(analyser.frequencyBinCount);
}
async function playTrack(id) {
 const track = library.find(t => t.id === id); if (!track) return;
 if (!queue.includes(id)) queue.push(id);
 if (current !== id) {
  media.pause(); if (activeURL) URL.revokeObjectURL(activeURL); activeURL = URL.createObjectURL(track.file); media.src = activeURL; current = id; subtitles = []; $('subtitle').textContent = '';
  $('stage').classList.toggle('video', /^video\//.test(track.type) || /\.(mp4|webm|mkv|mov)$/i.test(track.filename));
  $('trackTitle').textContent = track.name; $('trackArtist').textContent = `${track.filename.split('.').pop().toUpperCase()} · Local playback`; track.lastPlayed = Date.now(); storeFile(track).catch(() => {});
 }
 try { setupAudio(); await audioContext.resume(); await media.play(); } catch { toast('Playback unavailable. This preview uses browser codecs; try MP3, WAV, MP4 or WebM.'); }
 render();
}
function advance(direction) { if (!queue.length) return; const index = queue.indexOf(current); const next = shuffle && queue.length > 1 ? (index + 1 + Math.floor(Math.random() * (queue.length - 1))) % queue.length : (index + direction + queue.length) % queue.length; playTrack(queue[next]); }
$('play').onclick = async () => { if (!current) { if (queue.length) return playTrack(queue[0]); $('fileInput').click(); return; } if (media.paused) { try { setupAudio(); await audioContext.resume(); await media.play(); } catch { toast('Unable to play this file. Try another format.'); } } else media.pause(); };
media.onplay = () => { $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label', 'Pause'); $('stageStatus').textContent = 'AUDIO REACTIVE'; render(); restartVisualization(); };
media.onpause = () => { $('play').textContent = '▶'; $('play').setAttribute('aria-label', 'Play'); $('stageStatus').textContent = 'PAUSED'; render(); };
media.onended = () => { if (repeat || (queue.indexOf(current) >= 0 && queue.indexOf(current) < queue.length-1)) advance(1); };
media.onerror = () => toast('This format is not supported by this browser. Native codec support is planned.');
media.ontimeupdate = () => { $('elapsed').textContent = time(media.currentTime); $('duration').textContent = time(media.duration); $('seek').value = Number.isFinite(media.duration) && media.duration ? media.currentTime / media.duration * 1000 : 0; const cue = subtitles.find(c => media.currentTime >= c.start && media.currentTime < c.end); $('subtitle').textContent = cue?.text || ''; };
media.onloadedmetadata = () => $('duration').textContent = time(media.duration);
$('seek').oninput = () => { if (Number.isFinite(media.duration)) media.currentTime = +$('seek').value / 1000 * media.duration; };
media.volume = .7; $('volume').oninput = () => { media.volume = +$('volume').value; media.muted = false; $('mute').textContent = '◖))'; }; $('mute').onclick = () => { media.muted = !media.muted; $('mute').textContent = media.muted ? '◖×' : '◖))'; };
$('next').onclick = () => advance(1); $('previous').onclick = () => { if (media.currentTime > 3) media.currentTime = 0; else advance(-1); };
$('shuffle').onclick = () => { shuffle = !shuffle; $('shuffle').classList.toggle('enabled', shuffle); $('shuffle').setAttribute('aria-pressed', shuffle); };
$('repeat').onclick = () => { repeat = !repeat; $('repeat').classList.toggle('enabled', repeat); $('repeat').setAttribute('aria-pressed', repeat); };
$('favorite').onclick = () => { const track = library.find(t => t.id === current); if (!track) return toast('Play a file to favorite it'); track.favorite = !track.favorite; storeFile(track).catch(() => {}); render(); };
for (const id of ['import', 'addTracks']) $(id).onclick = () => $('fileInput').click(); $('fileInput').onchange = event => importFiles(event.target.files);
document.querySelectorAll('.nav').forEach(n => n.onclick = () => showView(n.dataset.view)); $('search').oninput = renderLibrary;
$('clearQueue').onclick = () => { queue = []; render(); };
function openPlaylistDialog(action) { dialogAction = action; $('playlistName').value = action === 'rename' ? playlists.find(p => p.id === selectedPlaylist).name : ''; $('playlistDialog').returnValue = ''; $('playlistDialog').showModal(); $('playlistName').focus(); }
$('newPlaylist').onclick = () => openPlaylistDialog('empty'); $('saveQueue').onclick = () => queue.length ? openPlaylistDialog('queue') : toast('Add files before saving your queue');
$('playlistDialog').addEventListener('close', () => { const name = $('playlistName').value.trim(); if ($('playlistDialog').returnValue !== 'save' || !name) return; if (dialogAction === 'rename') { playlists.find(p => p.id === selectedPlaylist).name = name; persist(); showView('playlist', selectedPlaylist); render(); return; } playlists.push({ id: crypto.randomUUID(), name, tracks: dialogAction === 'queue' ? [...queue] : [] }); persist(); render(); toast(`Created “${name}”${dialogAction === 'empty' ? ' · use + above the queue to save a filled playlist' : ''}`); });
$('exportQueue').onclick = () => { if (!queue.length) return toast('Your queue is empty'); const content = '#EXTM3U\n' + queue.map(id => library.find(t => t.id === id)).filter(Boolean).map(t => `#EXTINF:-1,${t.name.replace(/[\r\n]/g,' ')}\n${t.filename.replace(/[\r\n]/g,' ')}`).join('\n'); const url = URL.createObjectURL(new Blob([content], { type: 'audio/x-mpegurl' })); const a = document.createElement('a'); a.href = url; a.download = 'FireMedia.m3u'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast('Exported filenames. Keep the M3U beside your media files.'); };
$('focus').onclick = () => { showView('stage'); document.body.classList.toggle('focus'); $('focus').textContent = document.body.classList.contains('focus') ? 'Exit focus' : '⛶ Focus mode'; toast('Press Escape to leave focus mode'); };
$('toggleQueue').onclick = () => document.body.classList.toggle('queue-hidden');
document.addEventListener('keydown', event => { if (event.key === 'Escape') document.body.classList.remove('focus'); if (event.code === 'Space' && !/INPUT|SELECT|BUTTON|TEXTAREA/.test(event.target.tagName) && !$('playlistDialog').open) { event.preventDefault(); $('play').click(); } });
document.body.ondragover = event => event.preventDefault(); document.body.ondrop = event => { event.preventDefault(); if (event.dataTransfer.files.length) importFiles(event.dataTransfer.files); };
frequencies.forEach((f,i) => { const label = textNode('label', '', 'eq-band'); const input = document.createElement('input'); Object.assign(input, { type: 'range', min: '-12', max: '12', value: '0', step: '1' }); input.setAttribute('aria-label', `${f} Hz equalizer gain`); input.oninput = () => { if (filters[i]) filters[i].gain.setTargetAtTime(+input.value, audioContext.currentTime, .02); input.title = `${input.value} dB`; }; label.append(input, textNode('span', f >= 1000 ? `${f/1000}k` : f)); $('eq').append(label); });
$('resetEq').onclick = () => document.querySelectorAll('.eq input').forEach(input => { input.value = 0; input.oninput(); });
$('loadSubtitles').onclick = () => { if (!current) return toast('Open media before loading subtitles'); $('subtitleInput').click(); };
const cueTime = value => { const parts = value.replace(',', '.').split(':').map(Number); return parts.reduce((total, part) => total * 60 + part, 0); };
function parseSubtitles(content) { const cues = []; for (const block of content.replace(/\r/g,'').split(/\n\s*\n/)) { const lines = block.split('\n'); const timing = lines.findIndex(line => line.includes('-->')); if (timing < 0) continue; const [start,end] = lines[timing].split('-->').map(t => cueTime(t.trim().split(/\s/)[0])); if (Number.isFinite(start) && Number.isFinite(end) && end > start) cues.push({ start, end, text: lines.slice(timing+1).join('\n').replace(/<[^>]*>/g, '') }); } return cues.sort((a,b) => a.start-b.start); }
$('subtitleInput').onchange = async event => { const file = event.target.files[0]; if (!file) return; subtitles = parseSubtitles(await file.text()); toast(`Loaded ${subtitles.length} subtitle cues`); event.target.value = ''; };
$('videoEffects').onclick = () => $('videoDialog').showModal();
function applyVideoEffects() { media.style.filter = `brightness(${$('brightness').value}%) contrast(${$('contrast').value}%) saturate(${$('saturation').value}%)`; }
for (const id of ['brightness','contrast','saturation']) $(id).oninput = applyVideoEffects;
$('resetVideo').onclick = () => { for (const id of ['brightness','contrast','saturation']) $(id).value = 100; applyVideoEffects(); };
$('subtitleStyle').onchange = () => $('subtitle').className = `subtitle ${$('subtitleStyle').value}`;
$('physics').checked = preferences.physics ?? true; $('tension').value = preferences.tension ?? 65; $('particles').value = preferences.particles ?? 70;
for (const id of ['tension','particles']) { $(id+'Value').textContent = $(id).value + '%'; $(id).oninput = () => { $(id+'Value').textContent = $(id).value + '%'; savePreferences(); }; }
$('physics').onchange = () => { $('physicsLabel').textContent = $('physics').checked ? '↗  SPRING PHYSICS' : '≋  DIRECT RESPONSE'; savePreferences(); };
$('palette').onclick = () => { paletteIndex = (paletteIndex + 1) % palettes.length; $('palette').querySelectorAll('i').forEach((dot,i) => dot.style.background = `hsl(${palettes[paletteIndex][i]} 80% 70%)`); };
function selectPreset(name) { preset = name; document.querySelectorAll('[data-preset]').forEach(b => b.classList.toggle('selected', b.dataset.preset === name)); $('stage').querySelector('.stage-tag').textContent = `${name.toUpperCase()} / 0${['fireworks','aurora','spectrum'].indexOf(name)+1}`; savePreferences(); }
$('presets').onclick = event => { const button = event.target.closest('[data-preset]'); if (button) selectPreset(button.dataset.preset); }; selectPreset(preset);
function updateQuality() {
 lowDetail = ldmMode === 'on' || (ldmMode === 'auto' && (powerSaver || batteryLow || reducedMotion.matches || connection?.saveData));
 if (lowDetail) sparks.length = 0;
 $('qualityStatus').textContent = lowDetail ? '24 BARS · LOW DETAIL' : '64 BARS · PARTICLES ON';
 $('ldmDescription').textContent = lowDetail ? 'Low detail · fewer bars, no particles, pauses out of focus' : ldmMode === 'auto' ? 'Full detail · power-saver signal unavailable in browser' : 'Full detail · all effects enabled';
 if (ldmMode === 'auto' && lowDetail) $('ldmDescription').textContent = `Auto · ${powerSaver ? 'system power saver' : batteryLow ? 'low battery' : reducedMotion.matches ? 'reduced motion' : 'data saver'} · effects reduced`;
 document.querySelectorAll('[data-mode]').forEach(b => { b.classList.toggle('selected', b.dataset.mode === ldmMode); b.setAttribute('aria-pressed', b.dataset.mode === ldmMode); });
 savePreferences(); resizeCanvas(); restartVisualization();
}
$('ldm').onclick = event => { const b = event.target.closest('[data-mode]'); if (b) { ldmMode = b.dataset.mode; updateQuality(); } };
window.addEventListener('firemedia-power-saver', event => { powerSaver = event.detail?.enabled === true; updateQuality(); });
reducedMotion.addEventListener('change', updateQuality); connection?.addEventListener('change', updateQuality);
if (navigator.getBattery) navigator.getBattery().then(battery => { const update = () => { batteryLow = !battery.charging && battery.level <= .2; updateQuality(); }; battery.addEventListener('levelchange', update); battery.addEventListener('chargingchange', update); update(); }).catch(() => {});
const canvas = $('visualizer'), ctx = canvas.getContext('2d'); let width = 1, height = 1;
function resizeCanvas() { const r = canvas.getBoundingClientRect(); width = r.width; height = r.height; const scale = Math.min(devicePixelRatio || 1, lowDetail ? 1 : 2); canvas.width = width * scale; canvas.height = height * scale; ctx.setTransform(scale,0,0,scale,0,0); if (width && height) restartVisualization(); }
new ResizeObserver(resizeCanvas).observe($('stage'));
function shouldAnimate() { return !document.hidden && view === 'stage' && !(lowDetail && !document.hasFocus()); }
function restartVisualization() { if (frameId !== null) cancelAnimationFrame(frameId); frameId = null; lastTime = 0; canvas.style.visibility = lowDetail && (!document.hasFocus() || document.hidden) ? 'hidden' : 'visible'; if (shouldAnimate()) frameId = requestAnimationFrame(draw); }
for (const event of ['visibilitychange']) document.addEventListener(event, restartVisualization); window.addEventListener('blur', restartVisualization); window.addEventListener('focus', restartVisualization);
function draw(now) {
 frameId = null; if (!shouldAnimate()) return;
 const minInterval = lowDetail ? 1000/30 : 1000/60;
 if (lastTime && now-lastTime < minInterval-1) { frameId = requestAnimationFrame(draw); return; }
 const dt = Math.min((now - (lastTime || now-16.67))/1000, .05); lastTime = now; simulationTime += dt;
 const t = simulationTime, n = lowDetail ? 24 : 64, base = height - 38, barWidth = (width-70)/n;
 ctx.clearRect(0,0,width,height);
 const glow = ctx.createRadialGradient(width*.5,height*.8,0,width*.5,height*.65,width*.65); glow.addColorStop(0,preset === 'aurora' ? '#193b332c' : '#49295335'); glow.addColorStop(1,'#090b1000'); ctx.fillStyle = glow; ctx.fillRect(0,0,width,height);
 ctx.strokeStyle = '#9d99b309'; ctx.lineWidth = 1; for(let x=35;x<width;x+=35){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke();}
 const playing = !!analyser && !media.paused; if (playing) analyser.getByteFrequencyData(bins);
 for (let i=0;i<n;i++) {
  const normalized = i/(n-1); const bin = analyser ? Math.min(bins.length-1, Math.floor(2 * Math.pow(bins.length/3, normalized))) : 0;
  const value = playing ? bins[bin]/255 : current ? .025 : (.2 + .24*(Math.sin(i*1.71+t*2)+1)/2 + .22*(Math.sin(i*.34-t*1.3)+1)/2) * (.4+.6*Math.sin(Math.PI*normalized));
  const target = 4 + value * height * .55; const spring = springs[i];
  if ($('physics').checked) { const k = 40 + +$('tension').value * 2; spring.v += ((target-spring.y)*k - spring.v*13)*dt; spring.y = Math.max(0,spring.y+spring.v*dt); } else spring.y = target;
  const h = Math.min(height*.7, spring.y), x = 35 + i*barWidth, hue = palettes[paletteIndex][0] + normalized*(palettes[paletteIndex][4]-palettes[paletteIndex][0]);
  const grad = ctx.createLinearGradient(0,base-h,0,base); grad.addColorStop(0,`hsla(${hue},80%,75%,.95)`); grad.addColorStop(1,`hsla(${hue},75%,40%,.12)`); ctx.fillStyle = grad;
  if (preset === 'aurora') { ctx.globalAlpha = .55; ctx.beginPath(); ctx.ellipse(x,base-h/2,barWidth*1.7,h/2,0,0,Math.PI*2); ctx.fill(); ctx.globalAlpha=1; }
  else { ctx.beginPath(); ctx.roundRect(x,base-h,Math.max(2,barWidth-3),h,[2,2,0,0]); ctx.fill(); }
  ctx.fillStyle=`hsla(${hue},85%,85%,.8)`; ctx.fillRect(x,base-h-5,Math.max(2,barWidth-3),2);
  if (!lowDetail && preset === 'fireworks' && value > .26 && Math.random() < +$('particles').value/100*dt*3 && sparks.length<260) sparks.push({x:x+barWidth/2,y:base-h,vx:(Math.random()-.5)*40,vy:-35-Math.random()*85,life:1,hue});
 }
 if (!lowDetail && preset !== 'spectrum') {
  for (let i=sparks.length-1;i>=0;i--) { const p=sparks[i];p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy+=48*dt;p.life-=dt*.65;if(p.life<=0){sparks.splice(i,1);continue;}ctx.fillStyle=`hsla(${p.hue},90%,82%,${p.life*.8})`;ctx.beginPath();ctx.arc(p.x,p.y,1.2,0,Math.PI*2);ctx.fill();if(p.life>.7){ctx.fillRect(p.x-3,p.y-.35,6,.7);ctx.fillRect(p.x-.35,p.y-3,.7,6);}}
  for(let i=0;i<24;i++){const x=(i*127.7)%width,y=((i*53-t*(4+i%4))%height+height)%height;ctx.fillStyle=`rgba(196,174,224,${.1+(.1*Math.sin(t+i))})`;ctx.fillRect(x,y,1.3,1.3);}
 }
 ctx.strokeStyle='#9cafb022';ctx.beginPath();ctx.moveTo(28,base+7);ctx.lineTo(width-28,base+7);ctx.stroke();
 frameId=requestAnimationFrame(draw);
}
updateQuality(); restoreLibrary(); render();
