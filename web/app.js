'use strict';

const $ = (s, root = document) => root.querySelector(s);
const escapeHTML = (value = '') => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const e = escapeHTML;
const icons = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
  layers:'<path d="m12 3 10 5-10 5L2 8l10-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  settings:'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  back:'<path d="M19 12H5m6-6-6 6 6 6"/>',
  upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/>',
  down:'<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  image:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 5 5 3-3 4 4"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  link:'<path d="m10 13 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m0 12a4 4 0 0 0 6 0l5-5a4 4 0 0 0-6-6l-1 1" transform="translate(1 0) scale(.9)"/>',
  folder:'<path d="M3 6h7l2 3h9v11H3V6Z"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  play:'<path d="m8 5 11 7-11 7V5Z"/>',
};
const icon = (name, cls='') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.spark}</svg>`;
const state = {projects:[], recipes:[], jobs:[], settings:{}, platforms:[], project:null, tab:'photos', filter:'all', search:'', busy:false, dirty:false, importing:false};
const roles = ['开场','人物','环境','细节','转场','收尾'];
let saveTimer, saveQueue = Promise.resolve(), toastTimer, dragId, polling = false;
const date = value => new Intl.DateTimeFormat('zh-CN',{month:'short',day:'numeric'}).format(new Date(value));
const dateTime = value => new Intl.DateTimeFormat('zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(value));
const media = asset => '/media/' + (asset.preview || asset.file);

async function api(path, body, method) {
  const response = await fetch('/api' + path, {method:method || (body ? 'POST':'GET'), headers:body ? {'Content-Type':'application/json'}:{}, body:body ? JSON.stringify(body):undefined});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作失败，请重试。');
  return result;
}
function toast(text, error=false) {
  const target = $('#toast'); target.textContent = text; target.className = 'show' + (error ? ' error':'');
  if(error && $('#modal').open){let message=$('.form-error',$('#modal'));if(!message){message=document.createElement('p');message.className='form-error';message.setAttribute('role','alert');$('.modal-body',$('#modal')).prepend(message);}message.textContent=text;}
  clearTimeout(toastTimer); toastTimer = setTimeout(() => target.className='', error ? 7000:3500);
}
function badge(text, kind='') {return `<span class="badge ${kind}">${e(text)}</span>`;}
function button(action, text, name='', cls='secondary', extra='') {return `<button type="button" class="button ${cls}" data-action="${action}" ${extra}>${name ? icon(name):''}${text}</button>`;}
function platformChoices(selected=['xiaohongshu'],name='platforms') {
  return `<div class="platform-choice-grid">${state.platforms.map(platform=>`<label class="platform-choice"><input type="checkbox" name="${name}" value="${e(platform.id)}" ${selected.includes(platform.id)?'checked':''}><span><b>${e(platform.name)}</b><small>${e(platform.format)}</small></span></label>`).join('')}</div>`;
}
function platformLabel(id) {return state.platforms.find(platform=>platform.id===id)?.name || id || '小红书';}
function platformLabels(project) {return (project.platforms||[]).map(platformLabel).join('、') || project.platform || '小红书';}
function activeJob() {return state.jobs.find(j => j.project_id === state.project?.id && ['running','queued'].includes(j.status));}
function nav() {
  const section = location.hash.split('/')[1] || 'library';
  return `<aside class="sidebar"><a class="brand" href="#/library" aria-label="Photo Maker 首页"><span class="brand-symbol"><i></i><i></i><i></i><i></i></span><span>photo<span class="brand-light">maker</span><small>YOUR CREATIVE SPACE</small></span></a>
    <div class="workspace-label">个人工作空间 <span>LOCAL</span></div>
    <nav aria-label="主要导航">${[['library','grid','作品库'],['styles','layers','风格配方'],['activity','clock','创作任务']].map(([id,i,label])=>`<a href="#/${id}" class="nav-item ${section===id||id==='library'&&section==='project'?'active':''}">${icon(i)}${label}${id==='library'?`<span class="nav-count">${state.projects.filter(p=>!p.archived).length}</span>`:''}${id==='activity'&&state.jobs.some(j=>j.status==='running')?'<span class="running-dot"></span>':''}</a>`).join('')}</nav>
    <div class="sidebar-note"><span class="note-mark">✳</span><p>每一次创作，<br>都值得留下来。</p><small>素材、灵感与版本，<br>在这里慢慢积累。</small></div>
    <div class="sidebar-bottom"><a href="#/settings" class="nav-item ${section==='settings'?'active':''}">${icon('settings')}连接设置<span class="connection-dot ${state.settings.ai_configured?'connected':''}"></span></a><div class="profile"><span class="avatar">O</span><div>我的工作室<small><span class="tiny-dot"></span> 本地存储 · v0.1</small></div></div></div></aside>`;
}
function layout(content, title='创作工作空间', breadcrumb='') {
  $('#app').innerHTML = `${nav()}<div class="page"><header class="topbar"><div class="breadcrumb">${icon('folder')}<a href="#/library">工作空间</a><span>/</span>${e(breadcrumb||title)}</div><div class="top-right"><span class="local-indicator"><span class="tiny-dot"></span> 本地优先</span><span class="avatar small">O</span></div></header><main id="main" tabindex="-1">${content}</main><footer>PHOTO MAKER <span>为照片留出成为作品的空间。</span><span>本地创作工作台 · 0.1</span></footer></div>`;
  $('#main').inert = state.importing;
}
function projectCard(project) {
  const cover = project.assets.find(a=>a.selected)||project.assets[0];
  return `<article class="project-card"><a href="#/project/${project.id}" class="project-cover">${cover?`<img src="${media(cover)}" alt="${e(project.title)}" loading="lazy">`:`<div class="blank-cover">${icon('image')}<span>故事从第一张照片开始</span></div>`}<span class="cover-count">${icon('image')}${project.assets.length} 张</span>${project.status==='published'?badge('已发布','cover-status'):badge('创作中','cover-status neutral')}</a><div class="project-card-info"><a href="#/project/${project.id}"><h3>${e(project.title)}</h3></a><div class="project-meta"><span>${e(platformLabels(project))}<i>·</i>${project.versions} 个版本</span><span>${date(project.updated_at)}</span></div></div></article>`;
}
function library() {
  const all = state.projects.filter(p=>!p.archived), count = all.length, published=all.filter(p=>p.status==='published').length;
  const items = state.projects.filter(p=>state.filter==='archived'?p.archived:!p.archived).filter(p=>state.filter==='published'?p.status==='published':state.filter==='draft'?p.status==='draft':true).filter(p=>(p.title+' '+p.brief).toLowerCase().includes(state.search.toLowerCase()));
  layout(`<div class="heading"><div><div class="eyebrow">THE CREATIVE ARCHIVE</div><h1>你的照片，下一段故事<span class="orange-period">。</span></h1><p>从灵感到发布，把每一次创作好好收藏。</p></div>${button('new-project','新建作品','plus','primary')}</div>
    <section class="hero"><div class="hero-copy"><span class="hero-tag">A LITTLE SPACE FOR BIG IDEAS</span><h2>不止一张好照片。<br>是一组有你风格的作品。</h2><p>整理照片，找到叙事，让喜欢的风格<br class="desktop-break">成为下一次创作的起点。</p><div class="hero-actions">${button('new-project','开始一个新故事','arrow','dark')}${button('sample','体验海边示例','','text-button')}</div><span class="hero-footnote">${icon('layers')} 保留原片 · 保存版本 · 复用风格</span></div><div class="hero-art" aria-label="已有海边设计作品预览"><div class="photo-print print-back"><img src="/example/3" alt="海面光影示例"><small>03 / LIGHT ON WATER</small></div><div class="photo-print print-front"><img src="/example/1" alt="海边风车与潮汐示例"><small>01 / A NOTE FROM THE SEA</small></div><span class="hand-note">collect moments, make stories.</span><span class="art-coordinate">33° N &nbsp; 126° E<br>AN EXISTING DESIGN STUDY</span></div></section>
    <section class="stats" aria-label="工作室统计"><div><span class="stat-icon">${icon('grid')}</span><span><b>${count.toString().padStart(2,'0')}</b><small>创作项目</small></span></div><div><span class="stat-icon">${icon('check')}</span><span><b>${published.toString().padStart(2,'0')}</b><small>已发布作品</small></span></div><div><span class="stat-icon">${icon('layers')}</span><span><b>${state.recipes.length.toString().padStart(2,'0')}</b><small>可复用风格</small></span></div><p>好作品的背后，<br>是每一次细小的选择。<span>✳</span></p></section>
    <section class="library-section"><div class="section-heading"><h2>作品档案 <span>${count}</span></h2><label class="search">${icon('search')}<input id="project-search" type="search" placeholder="搜索作品或创作要求" aria-label="搜索作品" value="${e(state.search)}"></label></div><div class="filter-row"><div class="filters">${[['all','全部作品'],['draft','创作中'],['published','已发布'],['archived','已收纳']].map(([id,t])=>`<button class="filter ${state.filter===id?'active':''}" data-action="filter" data-id="${id}">${t}</button>`).join('')}</div><span class="sort-label">最近更新 ${icon('down')}</span></div><div class="project-grid">${items.map(projectCard).join('')}${!state.search&&state.filter==='all'?`<button class="new-project-card" data-action="new-project"><span>${icon('plus')}</span><b>新的故事，从这里开始</b><small>导入照片，开启一次创作</small></button>`:''}</div>${!items.length&&state.filter!=='all'?'<div class="empty-small">'+icon('folder')+'<p>这里还没有作品。</p></div>':''}</section>`, '作品库');
}
function projectView() {
  const p=state.project, selected=p.assets.filter(a=>a.selected), job=activeJob(), recipe=state.recipes.find(r=>r.id===p.recipe_id);
  const tabs=[['photos','素材与选片',p.assets.length],['story','图文编排',null],['versions','版本记录',p.versions.length],['publish','发布归档',p.publications.length]];
  layout(`<div class="project-heading"><div><a class="back-link" href="#/library">${icon('back')}返回作品库</a><div class="project-title-line"><h1>${e(p.title)}</h1>${badge(p.status==='published'?'已有发布版':'创作中',p.status==='published'?'green':'')}</div><p><span id="platform-summary">${e(platformLabels(p))}</span><i>·</i><span id="save-state">${state.dirty?'正在保存…':'已保存到本地'}</span><i>·</i>${selected.length} / ${p.assets.length} 张已选</p></div><div class="heading-actions">${button('project-options','更多','more')}${button('save-version','保存版本','layers')}${button('export','导出多平台素材包','down','primary')}</div></div>
    <div class="workspace-grid"><div class="work-panel"><div class="tabs" role="tablist">${tabs.map(([id,t,c])=>`<button role="tab" aria-selected="${state.tab===id}" class="tab ${state.tab===id?'active':''}" data-action="tab" data-id="${id}">${t}${c!==null?`<span>${c}</span>`:''}</button>`).join('')}</div><div class="tab-content">${state.tab==='photos'?photos(p):state.tab==='story'?story(p):state.tab==='versions'?versions(p):publication(p)}</div></div>
    <aside class="director-panel"><div class="director-title"><span class="director-avatar">${icon('spark')}</span><div><h2>创作总监</h2><small>让每个环节，围绕同一个故事</small></div></div><div class="connection-status">${state.settings.ai_configured?'<span class="tiny-dot"></span> 模型已配置 · 按需调用专家':'<span class="tiny-dot gray"></span> 本地模式 · 尚未连接 AI'}<a href="#/settings">设置 ${icon('arrow')}</a></div><label class="field"><span>这次，你想讲什么？</span><textarea id="brief" rows="4" placeholder="例如：用海边照片做一组安静、有电影感的图文。保留人物，也加入环境与细节。">${e(p.brief)}</textarea></label><fieldset class="platform-field"><legend>发布平台 <small>选择后按平台分包</small></legend>${platformChoices(p.platforms||['xiaohongshu'])}</fieldset><div class="director-tools">${button('plan-ai','AI 专家协作','spark','primary full',state.settings.ai_configured&&!job?'':`disabled title="${job?'请等待当前任务完成':'请先连接模型服务'}"`)}${button('plan-local','生成本地选片草案','grid','secondary full',job?'disabled':'')}<small>本地草案仅依据采样对比度，不理解照片内容。AI 调用按你的服务配置计费。</small></div>
    <div class="divider"></div><div class="mini-heading"><h3>风格配方</h3><a href="#/styles">查看全部 ${icon('arrow')}</a></div><label class="sr-only" for="project-recipe">项目风格</label><select id="project-recipe"><option value="">保留原片 / 未应用配方</option>${state.recipes.map(r=>`<option value="${r.id}" ${r.id===p.recipe_id?'selected':''}>${e(r.name)}</option>`).join('')}</select>${recipe?`<p class="recipe-description">${e(recipe.description)}</p>${badge(recipe.workflow&&Object.keys(recipe.workflow).length?'含 ComfyUI 工作流':'提示词配方')}`:'<p class="recipe-description">保存一次成功的创作方法，<br>下次就可以从这里继续。</p>'}${button('run-comfy','用首张已选照片试风格','play','secondary full',job||!recipe?.workflow||!Object.keys(recipe.workflow).length||!state.settings.comfy_configured?'disabled':'')}
    <div class="divider"></div><div class="mini-heading"><h3>工作记录</h3><span class="micro-label">LIVE</span></div><div id="job-log">${jobLog(p.id)}</div><div class="director-bottom">${icon('info')} 专家提案会保存为新版本。<br>发布前，由你做最后决定。</div></aside></div>`,p.title,'作品库 / '+p.title);
}
function photos(p) {
  return `<div class="panel-heading"><div><h2>为故事找到合适的画面</h2><p>勾选保留，拖动排序。第一张已选照片将成为封面。</p></div>${button('import','导入照片','plus')}</div><input id="file-input" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden>
    <div class="dropzone ${p.assets.length?'compact':''}" id="dropzone" tabindex="0" role="button" aria-label="导入照片"><span class="upload-symbol">${icon('upload')}</span><div><b>${state.importing?'正在导入照片…':'拖入照片，或点击选择'}</b><p>JPG、PNG、WebP · 单张不超过 25 MB · 原片本地保存</p></div><span class="drop-plus">${icon('plus')}</span></div>
    ${p.assets.length?`<div class="photo-toolbar"><span>${p.assets.filter(a=>a.selected).length} 张已选 <i>·</i> ${p.assets.length} 张素材</span><div><button class="text-action" data-action="select-all">全选</button><button class="text-action" data-action="select-none">取消全选</button></div></div><div class="asset-grid">${p.assets.map((a,i)=>assetCard(a,i)).join('')}</div>`:`<div class="photo-empty"><span>01</span><h3>把零散的瞬间，带进来。</h3><p>你的原片不会被覆盖。选片、改图和编排，<br>都会留下可以继续的版本。</p></div>`}`;
}
function assetCard(a,i) {
  const f=a.features||{};
  return `<article class="asset-card ${a.selected?'selected':''}" draggable="true" data-asset="${a.id}"><div class="asset-image"><button class="image-open" data-action="preview" data-id="${a.id}" aria-label="查看 ${e(a.name)}"><img src="${media(a)}" alt="${e(a.name)}" loading="lazy"></button><button class="select-check ${a.selected?'checked':''}" data-action="toggle-photo" data-id="${a.id}" aria-label="${a.selected?'取消选择':'选择'} ${e(a.name)}" aria-pressed="${a.selected}">${a.selected?icon('check'):''}</button><span class="asset-number">${String(i+1).padStart(2,'0')}</span>${a.origin==='comfyui'?'<span class="generated-label">风格输出</span>':''}</div><div class="asset-info"><b title="${e(a.name)}">${e(a.name)}</b><div class="asset-detail"><span>${f.width?`${f.width} × ${f.height}`:Math.round(a.size/1024)+' KB'}</span><select data-role-id="${a.id}" aria-label="${e(a.name)} 的叙事角色">${roles.map(r=>`<option ${a.role===r?'selected':''}>${r}</option>`).join('')}</select></div>${f.palette?`<div class="palette">${f.palette.map(c=>/^#[0-9a-f]{6}$/i.test(c)?`<span style="background:${c}"></span>`:'').join('')}<small>采样色彩</small></div>`:''}<div class="asset-order"><button data-action="move-left" data-id="${a.id}" ${i===0?'disabled':''} aria-label="前移 ${e(a.name)}">${icon('back')}</button><span>拖动排序</span><button data-action="move-right" data-id="${a.id}" ${i===state.project.assets.length-1?'disabled':''} aria-label="后移 ${e(a.name)}">${icon('arrow')}</button></div></div></article>`;
}
function story(p) {
  const selected=p.assets.filter(a=>a.selected);
  return `<div class="panel-heading"><div><h2>把画面，连成故事</h2><p>照片沿用选片顺序。文案可自由编辑，并随版本保存。</p></div>${badge('人工确认')}</div><div class="story-layout"><div class="phone-preview">${selected[0]?`<img src="${media(selected[0])}" alt="发布封面" class="story-cover">`:`<div class="story-cover no-image">${icon('image')}还没有封面</div>`}<div class="phone-body"><span class="phone-user"><span class="avatar small">O</span> 我的视觉日记</span><h3 id="story-preview-title">${e(p.story.title||p.title)}</h3><p id="story-preview-body">${e(p.story.body||'在右侧写下这组照片的故事。')}</p><small>${e(platformLabels(p))} · 预览</small></div></div><div class="story-fields"><label class="field"><span>作品标题</span><input id="story-title" placeholder="给这组照片一个名字" value="${e(p.story.title)}" maxlength="200"></label><label class="field"><span>正文</span><textarea id="story-body" rows="12" placeholder="从一个画面、一种感受，或者一句想说的话开始。">${e(p.story.body)}</textarea></label><label class="field"><span>创作备注 <small>不会混入发布正文</small></span><textarea id="story-notes" rows="4" placeholder="方案来源、待确认事项、调整方向…">${e(p.story.notes)}</textarea></label></div></div><h3 class="sequence-title">发布顺序 <span>${selected.length} 张</span></h3><div class="story-sequence">${selected.map((a,i)=>`<div><img src="${media(a)}" alt="${e(a.name)}"><small>${String(i+1).padStart(2,'0')} / ${e(a.role)}</small></div>`).join('')||'<p class="muted">先到素材页选几张照片。</p>'}</div>`;
}
function versions(p) {
  return `<div class="panel-heading"><div><h2>每一版，都有来处</h2><p>恢复历史版本时，会先自动保存当前状态。原图始终保留。</p></div>${button('save-version','保存当前版本','plus')}</div><div class="version-list">${[...p.versions].reverse().map(v=>`<article class="version-item"><span class="version-dot"></span><div class="version-main"><div class="version-top"><b>v${v.number} <span>${e(v.label)}</span></b>${badge(({ai:'AI 专家',local:'本地规则',manual:'手动',checkpoint:'自动快照',restore:'版本恢复',comfyui:'风格输出',publication:'发布版',example:'示例',duplicate:'作品副本'})[v.source]||v.source)}</div><p>${dateTime(v.created_at)}<i>·</i>${v.assets.filter(a=>a.selected).length} 张已选<i>·</i>${e(v.recipe?.name||'保留原片')}</p><div class="version-thumbs">${v.assets.filter(a=>a.selected).slice(0,6).map(a=>{const item=p.assets.find(x=>x.id===a.id);return item?`<img src="${media(item)}" alt="版本照片">`:'';}).join('')}</div><div class="version-story">${e(v.story.title||'尚未设置标题')}</div></div><div class="version-buttons">${button('view-version','查看','','text-button',`data-id="${v.id}"`)}${button('restore-version','恢复','','secondary',`data-id="${v.id}"`)}</div></article>`).join('')||`<div class="empty-small">${icon('layers')}<h3>为第一次创作留一个节点</h3><p>保存后，你就可以比较和恢复不同的创作版本。</p></div>`}</div>`;
}
function publication(p) {
  return `<div class="panel-heading"><div><h2>发布只是另一个起点</h2><p>导出后自行发布，再把链接和反馈留在这里。</p></div></div><div class="publish-callout"><span class="large-icon">${icon('check')}</span><div><h3>把这一版，正式归档</h3><p>保存当前选片、文案与风格快照。不会自动发布到社交平台。</p></div>${button('publish','登记发布','plus','primary')}</div><div class="publication-list">${[...p.publications].reverse().map(pub=>`<article class="publication-item"><div class="mini-heading"><h3>${e(pub.platform)} ${badge('v'+(p.versions.find(v=>v.id===pub.version_id)?.number||'?'),'green')}</h3><small>${dateTime(pub.published_at)}</small></div>${pub.url?`<a class="external-link" href="${e(pub.url)}" target="_blank" rel="noopener noreferrer">${icon('link')}查看已发布作品 ${icon('arrow')}</a>`:'<p class="muted">未填写发布链接</p>'}<label class="field"><span>反馈与下一次调整</span><textarea rows="3" data-feedback="${pub.id}" placeholder="记录浏览量、收藏、询问，或你对这次作品的新想法。">${e(pub.feedback)}</textarea></label><small class="muted">反馈由你手动记录，不会自动读取平台数据。</small></article>`).join('')}</div>`;
}
function jobLog(projectId) {
  const jobs=state.jobs.filter(j=>j.project_id===projectId).slice(0,2);
  if(!jobs.length)return '<div class="log-empty">创作任务的进度和结果，<br>会记录在这里。</div>';
  return jobs.map(j=>`<div class="job-entry"><div class="job-status">${j.status==='running'?'<span class="spinner"></span>':icon(j.status==='completed'?'check':'info')}<b>${j.kind==='comfyui'?'ComfyUI 风格执行':j.mode==='ai'?'AI 专家协作':'本地规则草案'}</b><span>${({running:'进行中',completed:'已完成',failed:'失败',queued:'排队中'})[j.status]}</span></div>${j.events.slice(-4).map(ev=>`<p>${e(ev.text)}</p>`).join('')}${j.error?`<p class="error-text">${e(j.error)}</p>`:''}</div>`).join('');
}
function stylesView() {
  layout(`<div class="heading"><div><div class="eyebrow">YOUR STYLE PLAYBOOK</div><h1>把喜欢的风格，留下来<span class="orange-period">。</span></h1><p>不止保存一张参考图，也保存让它再次发生的方法。</p></div>${button('new-recipe','新建风格配方','plus','primary')}</div><div class="styles-intro"><span class="style-flower">✳</span><div><h2>从一次灵感，到一套可复用的创作方法。</h2><p>记录视觉方向、正负提示词与 ComfyUI 工作流。工作流支持 <code>{{input_image}}</code>、<code>{{positive_prompt}}</code> 和 <code>{{negative_prompt}}</code> 占位符。</p></div></div><div class="recipe-grid">${state.recipes.map((r,i)=>`<article class="recipe-card"><div class="recipe-swatch swatch-${i%3}"><span>${String(i+1).padStart(2,'0')}</span>${icon('spark')}</div><div class="recipe-info">${badge(Object.keys(r.workflow||{}).length?'含 ComfyUI 工作流':'提示词配方')}<h3>${e(r.name)}</h3><p>${e(r.description||'尚未填写风格说明')}</p><small>${date(r.created_at)} 保存</small><div class="recipe-actions">${button('view-recipe','查看配方','','secondary',`data-id="${r.id}"`)}${button('reuse-recipe','用它开始新作品','arrow','text-button',`data-id="${r.id}"`)}</div></div></article>`).join('')}<button class="new-project-card recipe-add" data-action="new-recipe"><span>${icon('plus')}</span><b>收集你的下一种风格</b><small>提示词 · 视觉说明 · ComfyUI 配方</small></button></div>`, '风格配方');
}
function activityView() {
  layout(`<div class="heading"><div><div class="eyebrow">WORK IN PROGRESS</div><h1>每个任务，都有记录<span class="orange-period">。</span></h1><p>查看专家协作、生成过程与实际执行结果。</p></div>${button('refresh','刷新','clock')}</div><div class="activity-list">${state.jobs.map(j=>`<article class="activity-item"><div class="activity-label">${icon(j.kind==='comfyui'?'image':'spark')}<div><a href="#/project/${j.project_id}"><h3>${e(state.projects.find(p=>p.id===j.project_id)?.title||'作品')}</h3></a><small>${dateTime(j.created_at)}</small></div>${badge(({running:'进行中',completed:'已完成',failed:'失败'})[j.status]||j.status,j.status==='failed'?'red':j.status==='completed'?'green':'')}</div>${jobLogSingle(j)}</article>`).join('')||`<div class="empty-small">${icon('clock')}<h3>还没有创作任务</h3><p>在作品中运行本地草案或 AI 专家，过程就会出现在这里。</p></div>`}</div>`, '创作任务');
}
function jobLogSingle(j) {return `<div class="activity-events">${j.events.map(ev=>`<p><time>${dateTime(ev.time)}</time>${e(ev.text)}</p>`).join('')}${j.error?`<p class="error-text">${e(j.error)}</p>`:''}</div>`;}
function settingsView() {
  const s=state.settings;
  layout(`<div class="heading"><div><div class="eyebrow">MAKE IT YOURS</div><h1>连接你的创作工具<span class="orange-period">。</span></h1><p>可连接本地模型或兼容 Chat Completions 的 API 服务。</p></div></div>${platformPanel()}<form id="settings-form" class="settings-grid"><section class="settings-card"><div class="settings-card-head"><span class="settings-icon">${icon('spark')}</span><div><h2>AI 模型服务</h2><p>总监分派、选片师、艺术指导与图文编辑</p></div>${badge(s.ai_configured?'已配置':'未连接',s.ai_configured?'green':'')}</div><label class="field"><span>服务基础地址</span><input name="ai_base_url" type="url" placeholder="http://127.0.0.1:8000/v1" value="${e(s.ai_base_url||'')}"><small>填写包含 /v1 的基础地址，系统会调用 /chat/completions。</small></label><label class="field"><span>模型名称</span><input name="ai_model" placeholder="填写服务提供的模型 ID" value="${e(s.ai_model||'')}"></label><label class="field"><span>API Key</span><input name="ai_api_key" type="password" autocomplete="off" placeholder="${s.has_api_key?'已保存，留空保留原凭证':'本地免认证服务可留空'}"><small>凭证仅保存在本机，不会返回到浏览器页面。</small></label><label class="checkbox-field"><input name="ai_vision" type="checkbox" ${s.ai_vision?'checked':''}><span>启用图像理解<small>仅在模型支持图像输入时开启。每次最多发送前 12 张低分辨率预览；关闭时只发送文件信息和测量指标。</small></span></label><div class="settings-note">${icon('info')} AI 专家真实调用你的模型服务。设置后首次运行任务，即可验证模型与结构化输出兼容性。</div></section><section class="settings-card"><div class="settings-card-head"><span class="settings-icon peach">${icon('image')}</span><div><h2>ComfyUI</h2><p>本地或你自己的远程工作流服务</p></div></div><label class="field"><span>服务地址</span><input name="comfy_url" type="url" placeholder="http://127.0.0.1:8188" value="${e(s.comfy_url||'')}"></label>${button('test-comfy','检测已保存的连接','link')}<div id="comfy-test-result" aria-live="polite"></div><div class="settings-note">${icon('info')} 先在风格配方中导入 ComfyUI API 格式工作流，再到作品中选择配方并试运行。模型、LoRA 和节点需已安装在 ComfyUI。</div><div class="storage-note"><h3>${icon('folder')} 本地作品档案</h3><p>原片、预览图和项目数据库保存在本项目的 data 目录。导出发布包可获得选片、原片和完整项目记录。</p><p>当前版本面向个人本机使用。</p></div></section><div class="settings-save"><span>保存后即可在作品中使用。</span><button class="button primary" type="submit">${icon('check')}保存连接设置</button></div></form>`, '连接设置');
}
function xhsStatus() {return state.platforms.find(p=>p.id==='xiaohongshu')?.connection||{state:'disconnected',message:'未连接'};}
function xhsStatusText(status) {return ({disconnected:'未连接',starting:'打开窗口中',login_required:'等待你登录',verification_required:'需要人工验证',unknown:'正在确认',connected:'登录已检测',preparing:'正在准备草稿',ready_for_review:'草稿已填写 · 等待发布结果',published:'已确认发布',closing:'关闭中',error:'操作中断'})[status]||status;}
function platformPanel() {
  return `<section class="platform-integrations"><div class="panel-heading"><div><h2>发布平台</h2><p>小红书先行；抖音和微博目前支持素材导出，账号接入待实现。</p></div>${badge('3 个发布目标')}</div><div class="integration-grid">${state.platforms.map(p=>`<article class="integration-item"><div><h3>${e(p.name)}</h3>${badge(p.id==='xiaohongshu'?'浏览器辅助 · 实验版':'仅素材导出')}</div><p>${e(p.format)}</p>${p.id==='xiaohongshu'?`<div id="xhs-connection-status">${xhsConnectionControls()}</div>`:'<small>账号接入尚未实现</small>'}</article>`).join('')}</div><p class="xhs-risk">浏览器辅助不是官方授权接口，可能触发验证、限流或账号限制。<a href="https://agree.xiaohongshu.com/h5/terms/ZXXY20260422001/-1" target="_blank" rel="noopener noreferrer">查看平台协议</a>。你也可以继续导出素材后手动发布。</p></section>`;
}
function xhsConnectionControls() {
  const s=xhsStatus(),active=!['disconnected','error'].includes(s.state);
  return `<p class="xhs-state" role="status" aria-live="polite" aria-atomic="true">小红书：${e(xhsStatusText(s.state))}</p><p class="xhs-message">${e(s.message)}</p><div class="xhs-actions">${button('xhs-connect','打开登录窗口','link','secondary',active?'disabled':'')}${button('xhs-close','关闭连接','','secondary',s.state==='disconnected'?'disabled':'')}</div>${s.available===false?'<p class="xhs-message">请按 README 安装连接依赖，并使用 .venv/bin/python app.py 启动。</p>':''}`;
}
function draftPanel() {
  const s=xhsStatus();
  return `<section class="xhs-draft-panel"><h3>小红书图文草稿</h3><p>草稿填好后由你在官网发布。检测到官网成功提示后会更新状态；未检测到时，可以手动确认并登记。</p><div id="xhs-draft-status" role="status" aria-live="polite" aria-atomic="true"></div><div class="xhs-actions">${button('xhs-draft','准备小红书草稿','upload','secondary')}${button('xhs-record-publication','我已在官网发布 · 登记','check','secondary')}</div>${!s.account_connected?'<a href="#/settings">先到连接设置登录</a>':''}</section>`;
}
function modal(title, body, footer='') {
  const dialog=$('#modal');
  if(dialog.open)dialog.close();
  dialog.innerHTML=`<div class="modal-header"><div><div class="eyebrow">PHOTO MAKER</div><h2>${e(title)}</h2></div><button class="icon-button" data-action="close-modal" aria-label="关闭">${icon('close')}</button></div><div class="modal-body">${body}</div>${footer?`<div class="modal-footer">${footer}</div>`:''}`;
  dialog.showModal();
}
function newProjectModal(recipeId='') {
  modal('开始一个新故事',`<form id="new-project-form" data-recipe="${recipeId}"><label class="field"><span>作品名称</span><input name="title" required maxlength="140" placeholder="例如：海风经过的下午" autofocus></label><label class="field"><span>创作要求 <small>可稍后填写</small></span><textarea name="brief" rows="3" placeholder="想讲什么故事？给谁看？想保留怎样的感觉？"></textarea></label><fieldset class="platform-field"><legend>发布平台 <small>可多选，稍后可修改</small></legend>${platformChoices()}</fieldset><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">稍后再说</button><button type="submit" class="button primary">创建作品 ${icon('arrow')}</button></div></form>`);
}
function recipeModal(existing) {
  if(existing){
    modal(existing.name,`<p>${e(existing.description)}</p><label class="field"><span>正向提示词</span><textarea readonly rows="5">${e(existing.positive_prompt)}</textarea></label><label class="field"><span>负向提示词</span><textarea readonly rows="3">${e(existing.negative_prompt)}</textarea></label><details><summary>ComfyUI API 工作流</summary><pre>${e(JSON.stringify(existing.workflow,null,2))}</pre></details>`,button('reuse-recipe','用这个风格开始新作品','arrow','primary',`data-id="${existing.id}"`));return;
  }
  modal('保存一套风格配方',`<form id="recipe-form"><label class="field"><span>配方名称</span><input name="name" required maxlength="140" placeholder="例如：潮汐 · 柔和蓝调"></label><label class="field"><span>视觉说明</span><textarea name="description" rows="3" placeholder="色彩、光线、构图、颗粒、适用照片条件…"></textarea></label><label class="field"><span>正向提示词</span><textarea name="positive_prompt" rows="3" placeholder="soft cinematic light, muted ocean blue…"></textarea></label><label class="field"><span>负向提示词</span><textarea name="negative_prompt" rows="2" placeholder="oversaturated, distorted…"></textarea></label><label class="field"><span>ComfyUI API 工作流 <small>选填</small></span><input id="workflow-file" type="file" accept=".json,application/json"><textarea name="workflow" id="workflow-json" rows="5" spellcheck="false" placeholder='{"1":{"class_type":"…","inputs":{…}}}'></textarea><small>支持 {{input_image}}、{{positive_prompt}}、{{negative_prompt}} 替换。请导出 API 格式，而非画布界面格式。</small></label><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">取消</button><button type="submit" class="button primary">${icon('check')}保存风格配方</button></div></form>`);
}
function markDirty() {
  state.dirty=true; const label=$('#save-state');if(label)label.textContent='正在保存…';
  clearTimeout(saveTimer);saveTimer=setTimeout(()=>flush().catch(err=>toast(err.message,true)),550);
}
async function flush() {
  clearTimeout(saveTimer);
  if(!state.project||!state.dirty)return saveQueue;
  const p=state.project, payload={title:p.title,brief:p.brief,platform:p.platform,platforms:p.platforms,story:{...p.story},recipe_id:p.recipe_id,assets:p.assets.map(a=>({id:a.id,selected:a.selected,role:a.role}))};
  state.dirty=false;
  const task=saveQueue.catch(()=>{}).then(()=>api('/projects/'+p.id,payload,'PATCH')).then(result=>{
    if(state.project?.id===p.id){state.project.updated_at=result.updated_at;const label=$('#save-state');if(label)label.textContent=state.dirty?'正在保存…':'已保存到本地';}
    return result;
  }).catch(err=>{if(state.project?.id===p.id){state.dirty=true;const label=$('#save-state');if(label)label.textContent='保存失败 · 请重试';}throw err;});
  saveQueue=task;return task;
}
async function reloadProject() {
  await flush();state.project=await api('/projects/'+state.project.id);state.recipes=await api('/recipes');render();
}
async function refreshData() {
  const [projects,recipes,jobs,settings,platforms]=await Promise.all([api('/projects'),api('/recipes'),api('/jobs'),api('/settings'),api('/platforms')]);Object.assign(state,{projects,recipes,jobs,settings,platforms});
}
function render() {
  const section=location.hash.split('/')[1]||'library';
  if(section==='project'&&state.project)projectView();else if(section==='styles')stylesView();else if(section==='activity')activityView();else if(section==='settings')settingsView();else library();
  if(section==='project'&&state.tab==='publish'){$('.tab-content').insertAdjacentHTML('afterbegin',draftPanel());updateXhsStatus();}
}
let routeNumber=0;
async function route() {
  const number=++routeNumber;
  try{
    await flush();if(number!==routeNumber)return;
    await refreshData();if(number!==routeNumber)return;
    const [,section,id]=location.hash.split('/');
    if(section==='project'&&id){const project=await api('/projects/'+id);if(number!==routeNumber)return;state.project=project;state.tab='photos';}
    else state.project=null;
    state.dirty=false;render();window.scrollTo(0,0);
  }catch(err){toast(err.message,true);if(!$('#main'))layout(`<div class="empty-small"><h1>暂时无法打开工作空间</h1><p>${e(err.message)}</p>${button('refresh','重试')}</div>`);}
}
async function startJob(mode) {
  await flush();const job=await api('/projects/'+state.project.id+'/plan',{mode});state.jobs.unshift(job);render();toast(mode==='ai'?'专家正在处理，结果会保存为新版本。':'正在创建本地规则草案。');
}
async function onAction(action,el) {
  if(action==='close-modal'){$('#modal').close();return;}
  if(action==='xhs-connect'){modal('连接小红书 · 实验版',`<p>将打开独立的本机 Chrome 窗口，由你在小红书官方页面登录。会话只保存在本机；关闭窗口不会退出账号，下次连接仍需重新检测。</p><p class="xhs-risk">平台协议限制未经授权的第三方软件。浏览器辅助可能触发安全验证、限流或账号限制，人工点发布也不能保证无风险。</p>`,button('xhs-confirm-connect','了解风险，打开登录窗口','link','primary'));return;}
  if(action==='xhs-confirm-connect'){el.disabled=true;try{const status=await api('/connections/xiaohongshu',{action:'connect'});setXhsStatus(status);$('#modal').close();updateXhsStatus();}finally{if(el.isConnected)el.disabled=false;}return;}
  if(action==='xhs-close'){setXhsStatus(await api('/connections/xiaohongshu',{action:'close'}));updateXhsStatus();return;}
  if(action==='new-project'){newProjectModal();return;}
  if(action==='filter'){state.filter=el.dataset.id;library();return;}
  if(action==='sample'){await flush();el.disabled=true;const p=await api('/sample',{});location.hash='#/project/'+p.id;return;}
  if(action==='refresh'){await route();return;}
  if(action==='new-recipe'){recipeModal();return;}
  if(action==='view-recipe'){recipeModal(state.recipes.find(r=>r.id===el.dataset.id));return;}
  if(action==='reuse-recipe'){newProjectModal(el.dataset.id);return;}
  if(action==='test-comfy'){
    el.disabled=true;try{const result=await api('/connections/comfy',{});$('#comfy-test-result').textContent='已连接 '+(result.devices.map(d=>d.name).join('、')||'ComfyUI');}finally{el.disabled=false;}return;
  }
  const p=state.project;if(!p)return;
  if(action==='xhs-draft'){await flush();modal('将当前作品准备到小红书',`<p>将上传当前已选的 ${p.assets.filter(a=>a.selected).length} 张原图与标题、正文，第一张作为封面。创作备注不会上传。</p><p>不会自动裁切、添加话题关联或点击发布。请在官方窗口核对图片顺序、文案和 AI 内容标注。</p><p>准备后若继续修改本地作品，不会同步到网页草稿。请先在官网完成或放弃现有草稿，再关闭连接重新准备。</p>`,button('xhs-confirm-draft','确认上传并填写草稿','upload','primary'));return;}
  if(action==='xhs-confirm-draft'){el.disabled=true;try{await flush();setXhsStatus(await api('/projects/'+p.id+'/xhs-draft',{confirm_upload:true}));$('#modal').close();await reloadProject();}finally{if(el.isConnected)el.disabled=false;}return;}
  if(action==='tab'){await flush();state.tab=el.dataset.id;render();return;}
  if(action==='import'){$('#file-input').click();return;}
  if(action==='toggle-photo'){const asset=p.assets.find(a=>a.id===el.dataset.id);asset.selected=!asset.selected;markDirty();render();return;}
  if(action==='select-all'||action==='select-none'){p.assets.forEach(a=>a.selected=action==='select-all');markDirty();render();return;}
  if(action==='move-left'||action==='move-right'){
    const index=p.assets.findIndex(a=>a.id===el.dataset.id),to=index+(action==='move-left'?-1:1);
    if(to>=0&&to<p.assets.length){[p.assets[index],p.assets[to]]=[p.assets[to],p.assets[index]];markDirty();render();}return;
  }
  if(action==='preview'){
    const asset=p.assets.find(a=>a.id===el.dataset.id);
    modal(asset.name,`<img class="full-preview" src="/media/${asset.file}" alt="${e(asset.name)}"><div class="preview-meta">${badge(asset.origin==='comfyui'?'ComfyUI 输出':'原始素材')}<span>SHA-256 ${asset.sha256.slice(0,16)}…</span></div><p class="muted">${asset.parent_asset_id?'来源原片：'+e(p.assets.find(a=>a.id===asset.parent_asset_id)?.name||asset.parent_asset_id):'原文件按内容哈希保存，不会覆盖原片。'}</p>`);return;
  }
  if(action==='save-version'){
    modal('保存一个创作节点',`<form id="version-form"><label class="field"><span>版本说明</span><input name="label" required placeholder="例如：更安静的选片 / 调整封面" value="手动保存"></label><div class="form-actions"><button class="button primary" type="submit">${icon('layers')}保存版本</button></div></form>`);return;
  }
  if(action==='view-version'){
    const version=p.versions.find(v=>v.id===el.dataset.id);
    modal('v'+version.number+' · '+version.label,`<p class="muted">${dateTime(version.created_at)} · ${e(version.source)}</p><h3>${e(version.story.title||'未设置标题')}</h3><p class="preserve-lines">${e(version.story.body||'没有正文')}</p><div class="story-sequence">${version.assets.filter(a=>a.selected).map(a=>{const asset=p.assets.find(x=>x.id===a.id);return asset?`<div><img src="${media(asset)}" alt="${e(asset.name)}"><small>${e(a.role)}</small></div>`:'';}).join('')}</div><details><summary>来源与执行记录</summary><pre>${e(JSON.stringify({recipe:version.recipe,details:version.details},null,2))}</pre></details>`,button('restore-version','恢复这个版本','clock','primary',`data-id="${version.id}"`));return;
  }
  if(action==='restore-version'){
    await flush();state.project=await api('/projects/'+p.id+'/restore',{version_id:el.dataset.id});$('#modal').close();render();toast('已恢复，并保存了恢复前的快照。');return;
  }
  if(action==='export'){await flush();window.location.href='/api/projects/'+p.id+'/export';toast('正在导出原片、选片、文案与版本记录。');return;}
  if(action==='plan-local'||action==='plan-ai'){await startJob(action==='plan-ai'?'ai':'local');return;}
  if(action==='run-comfy'){
    const asset=p.assets.find(a=>a.selected);if(!asset)throw new Error('请先选择输入照片。');
    await flush();const job=await api('/projects/'+p.id+'/comfy',{asset_id:asset.id});state.jobs.unshift(job);render();toast('已提交 ComfyUI 任务，输出会作为新素材保存。');return;
  }
  if(action==='publish'||action==='xhs-record-publication'){
    modal('登记已发布作品',`<p class="muted">仅确认你已在官网完成发布并创建本地档案，不会再次上传或发布。归档内容为当前本地版本，请核对它与官网作品一致。</p><form id="publish-form"><fieldset class="platform-field"><legend>已发布到</legend>${platformChoices(action==='xhs-record-publication'?['xiaohongshu']:(p.platforms||['xiaohongshu']),'published_platforms')}</fieldset><label class="field"><span>作品链接 <small>选填</small></span><input name="url" type="url" placeholder="https://…"></label><label class="field"><span>发布备注</span><textarea name="feedback" rows="3" placeholder="记录这次发布的想法或待观察的反馈。"></textarea></label><div class="form-actions"><button type="submit" class="button primary">${icon('check')}确认已发布并保存档案</button></div></form>`);return;
  }
  if(action==='project-options'){
    modal('作品设置',`<form id="project-settings-form"><label class="field"><span>作品名称</span><input name="title" value="${e(p.title)}" required maxlength="140"></label><div class="form-actions"><button type="submit" class="button primary">保存名称</button></div></form><div class="options-actions">${button('duplicate','复制为新作品','layers')}${button('archive',p.archived?'移回作品库':'收纳这个项目','folder')}</div><p class="muted">收纳只会从默认列表隐藏，原片与所有版本都会保留。</p>`);return;
  }
  if(action==='duplicate'){await flush();const clone=await api('/projects/'+p.id+'/duplicate',{});$('#modal').close();location.hash='#/project/'+clone.id;toast('已复制素材和当前方案，创建了独立项目。');return;}
  if(action==='archive'){await flush();await api('/projects/'+p.id,{archived:!p.archived},'PATCH');$('#modal').close();location.hash='#/library';return;}
}
document.addEventListener('click',async event=>{
  const element=event.target.closest('[data-action]');if(!element||element.disabled)return;
  try{await onAction(element.dataset.action,element);}catch(err){toast(err.message,true);if(element.isConnected)element.disabled=false;}
});
document.addEventListener('submit',async event=>{
  const form=event.target;if(!form.id)return;event.preventDefault();const submit=form.querySelector('[type=submit]');if(submit)submit.disabled=true;
  const fields=Object.fromEntries(new FormData(form));
  try{
    if(form.id==='new-project-form'){
      fields.platforms=new FormData(form).getAll('platforms');if(!fields.platforms.length)throw new Error('至少选择一个发布平台。');fields.platform=platformLabel(fields.platforms[0]);const p=await api('/projects',fields);if(form.dataset.recipe)await api('/projects/'+p.id,{recipe_id:form.dataset.recipe},'PATCH');$('#modal').close();location.hash='#/project/'+p.id;
    }else if(form.id==='settings-form'){
      fields.ai_vision=form.elements.ai_vision.checked;if(!fields.ai_api_key)delete fields.ai_api_key;
      state.settings=await api('/settings',fields);render();toast('连接设置已保存。');
    }else if(form.id==='recipe-form'){
      try{fields.workflow=fields.workflow.trim()?JSON.parse(fields.workflow):{};}catch{throw new Error('工作流 JSON 格式不正确。');}
      await api('/recipes',fields);state.recipes=await api('/recipes');$('#modal').close();render();toast('风格配方已保存。');
    }else if(form.id==='version-form'){
      await flush();state.project=await api('/projects/'+state.project.id+'/versions',fields);$('#modal').close();render();toast('当前版本已保存。');
    }else if(form.id==='publish-form'){
      fields.platform_ids=new FormData(form).getAll('published_platforms');if(!fields.platform_ids.length)throw new Error('至少选择一个已经发布的平台。');await flush();state.project=await api('/projects/'+state.project.id+'/publish',fields);setXhsStatus(await api('/connections/xiaohongshu'));$('#modal').close();render();toast('已确认发布，并保存发布档案与版本快照。');
    }else if(form.id==='project-settings-form'){
      state.project.title=fields.title;markDirty();await flush();$('#modal').close();render();
    }
  }catch(err){toast(err.message,true);}finally{if(submit?.isConnected)submit.disabled=false;}
});
document.addEventListener('input',event=>{
  const element=event.target,p=state.project;
  if(element.id==='project-search'){
    const position=element.selectionStart;state.search=element.value;library();const search=$('#project-search');search.focus();try{search.setSelectionRange(position,position);}catch{}return;
  }
  if(!p)return;
  if(element.id==='brief'){p.brief=element.value;markDirty();}
  if(element.id==='story-title'){p.story.title=element.value;$('#story-preview-title').textContent=element.value||p.title;markDirty();}
  if(element.id==='story-body'){p.story.body=element.value;$('#story-preview-body').textContent=element.value;markDirty();}
  if(element.id==='story-notes'){p.story.notes=element.value;markDirty();}
});
document.addEventListener('change',async event=>{
  const element=event.target,p=state.project;
  try{
    if(element.id==='workflow-file'&&element.files[0]){const text=await element.files[0].text();JSON.parse(text);$('#workflow-json').value=text;}
    if(element.id==='file-input')await importFiles([...element.files]);
    if(!p)return;
    if(element.name==='platforms'&&element.closest('.director-panel')){p.platforms=[...document.querySelectorAll('.director-panel input[name="platforms"]:checked')].map(input=>input.value);if(!p.platforms.length){element.checked=true;p.platforms=[element.value];toast('至少保留一个发布平台。');}p.platform=platformLabel(p.platforms[0]);$('#platform-summary').textContent=platformLabels(p);markDirty();}
    if(element.id==='project-recipe'){p.recipe_id=element.value||null;markDirty();await flush();render();}
    if(element.dataset.roleId){p.assets.find(a=>a.id===element.dataset.roleId).role=element.value;markDirty();}
    if(element.dataset.feedback){await flush();state.project=await api('/projects/'+p.id+'/feedback',{publication_id:element.dataset.feedback,feedback:element.value});toast('反馈已保存。');}
  }catch(err){toast(err.message,true);}
});
const readFile = file => new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('读取图片失败。'));reader.readAsDataURL(file);});
async function prepareImage(file) {
  const bitmap=await createImageBitmap(file), width=bitmap.width,height=bitmap.height;
  const canvas=document.createElement('canvas');const scale=Math.min(1,640/Math.max(width,height));canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale));
  const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
  const preview=canvas.toDataURL('image/jpeg',.8).split(',')[1];
  const sample=document.createElement('canvas');sample.width=64;sample.height=64;const small=sample.getContext('2d',{willReadFrequently:true});small.drawImage(canvas,0,0,64,64);const pixels=small.getImageData(0,0,64,64).data;
  const values=[],buckets=new Map();let total=0,totalSq=0,edge=0;
  for(let i=0;i<pixels.length;i+=4){const r=pixels[i],g=pixels[i+1],b=pixels[i+2],light=.2126*r+.7152*g+.0722*b;values.push(light);total+=light;totalSq+=light*light;const key=[r,g,b].map(v=>Math.min(255,Math.round(v/48)*48));const str=key.join(',');buckets.set(str,(buckets.get(str)||0)+1);}
  for(let y=1;y<63;y++)for(let x=1;x<63;x++){const i=y*64+x;edge+=Math.abs(values[i]*4-values[i-1]-values[i+1]-values[i-64]-values[i+64]);}
  const mean=total/values.length;
  const palette=[...buckets].sort((a,b)=>b[1]-a[1]).slice(0,5).map(([key])=>'#'+key.split(',').map(n=>Number(n).toString(16).padStart(2,'0')).join(''));
  return {preview,features:{width,height,brightness:Math.round(mean/255*100),contrast:Math.round(Math.sqrt(Math.max(0,totalSq/values.length-mean*mean))/255*100),sharpness:Math.round(edge/(62*62)),palette}};
}
async function importFiles(files) {
  if(state.importing)return;const projectId=state.project?.id;if(!projectId)return;
  await flush();state.importing=true;render();let added=0,duplicates=0;const errors=[];
  for(let i=0;i<files.length;i++){
    const file=files[i];
    try{
      if(!['image/jpeg','image/png','image/webp'].includes(file.type))throw new Error('仅支持 JPG / PNG / WebP');
      if(file.size>25*1024*1024)throw new Error('超过 25 MB');
      const prepared=await prepareImage(file),data=await readFile(file);
      const result=await api('/projects/'+projectId+'/assets',{name:file.name,data,...prepared});
      if(result.duplicate)duplicates++;else added++;
      // Keep any edits made during upload rather than applying a stale server snapshot.
      if(state.project?.id===projectId){
        await flush();state.project=await api('/projects/'+projectId);render();
      }
      toast(`导入中 ${i+1} / ${files.length}`);
    }catch(err){errors.push(file.name+'：'+err.message);}
  }
  state.importing=false;if(state.project?.id===projectId){await reloadProject();}
  toast(`已导入 ${added} 张${duplicates?'，跳过 '+duplicates+' 张重复照片':''}${errors.length?'；'+errors.join('；'):''}`,!!errors.length);
}
document.addEventListener('dragstart',event=>{const card=event.target.closest('[data-asset]');if(card){dragId=card.dataset.asset;event.dataTransfer.setData('text/plain',dragId);event.dataTransfer.effectAllowed='move';card.classList.add('dragging');}});
document.addEventListener('dragend',()=>{dragId=null;document.querySelectorAll('.dragging,.dragover').forEach(el=>el.classList.remove('dragging','dragover'));});
document.addEventListener('dragover',event=>{const target=event.target.closest('#dropzone,[data-asset]');if(target){event.preventDefault();target.classList.add('dragover');}});
document.addEventListener('dragleave',event=>event.target.closest('#dropzone,[data-asset]')?.classList.remove('dragover'));
document.addEventListener('drop',async event=>{
  const target=event.target.closest('#dropzone,[data-asset]');if(!target)return;event.preventDefault();target.classList.remove('dragover');
  if(event.dataTransfer.files.length){await importFiles([...event.dataTransfer.files]);return;}
  if(dragId&&target.dataset.asset&&dragId!==target.dataset.asset){const assets=state.project.assets,from=assets.findIndex(a=>a.id===dragId),to=assets.findIndex(a=>a.id===target.dataset.asset);if(from>=0&&to>=0){assets.splice(to,0,assets.splice(from,1)[0]);markDirty();render();}}
});
document.addEventListener('click',event=>{if(event.target.closest('#dropzone'))$('#file-input')?.click();});
document.addEventListener('keydown',event=>{if(event.target.id==='dropzone'&&['Enter',' '].includes(event.key)){event.preventDefault();$('#file-input')?.click();}});
window.addEventListener('beforeunload',event=>{if(state.dirty||state.importing){event.preventDefault();event.returnValue='';}});
window.addEventListener('hashchange',route);
async function poll() {
  if(polling||!state.jobs.some(j=>['running','queued'].includes(j.status)))return;
  polling=true;
  try{
    const old=state.jobs, next=await api('/jobs');state.jobs=next;
    const finished=next.find(j=>['completed','failed'].includes(j.status)&&old.some(o=>o.id===j.id&&['running','queued'].includes(o.status)));
    if(finished){if(state.project?.id===finished.project_id){await reloadProject();}else if(location.hash.startsWith('#/activity'))render();toast(finished.error||'创作任务已完成，已保存结果。',!!finished.error);}
    else if(state.project&&$('#job-log'))$('#job-log').innerHTML=jobLog(state.project.id);
    else if(location.hash.startsWith('#/activity'))render();
  }catch(err){toast(err.message,true);}finally{polling=false;}
}
setInterval(poll,1500);
function setXhsStatus(status){const p=state.platforms.find(p=>p.id==='xiaohongshu');if(p){p.connection=status;p.account_connected=status.account_connected;}}
function updateXhsStatus(){
  const target=$('#xhs-connection-status');if(target)target.innerHTML=xhsConnectionControls();
  const draft=$('#xhs-draft-status');if(draft){const s=xhsStatus();draft.textContent='小红书：'+xhsStatusText(s.state)+'。'+(s.project_id&&s.project_id!==state.project?.id?'另一作品正在使用该窗口。':s.message);const b=$('[data-action="xhs-draft"]');if(b)b.disabled=s.state!=='connected'||!state.project?.platforms.includes('xiaohongshu');}
  const record=$('[data-action="xhs-record-publication"]');if(record){const s=xhsStatus();record.disabled=s.state==='preparing'&&s.project_id===state.project?.id;}
}
let xhsPolling=false;
setInterval(async()=>{if(xhsPolling||!['settings','project'].includes(location.hash.split('/')[1]))return;xhsPolling=true;try{setXhsStatus(await api('/connections/xiaohongshu'));updateXhsStatus();}catch{}finally{xhsPolling=false;}},2000);
route();
