/* Sandbox-frame office renderer. Runs ONLY inside /office/host.html which the
 * parent embeds with sandbox="allow-scripts" (opaque origin: no cookies, no
 * parent DOM, no network by meta CSP). Bundled to public/office/render.js. */
import JSZip from 'jszip'
import mammoth from 'mammoth/mammoth.browser'
import { init as initPptx } from 'pptx-preview'
import DOMPurify from 'dompurify'

const PURIFY = {
  USE_PROFILES: { html: true },
  FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'embed', 'form', 'base', 'link', 'meta'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'formaction', 'srcset'],
  ALLOW_DATA_ATTR: false,
}

function el(tag: string, cls: string, text?: string): HTMLElement {
  const n = document.createElement(tag)
  if (cls) n.className = cls
  if (text !== undefined) n.textContent = text
  return n
}

async function renderDocx(bytes: ArrayBuffer, stage: HTMLElement) {
  const res = await (mammoth as any).convertToHtml({ arrayBuffer: bytes })
  const clean = DOMPurify.sanitize(res.value as string, PURIFY) as string
  const box = el('div', 'docx-body')
  box.innerHTML = clean // DOMPurify-sanitized; opaque frame; no scripts survive
  stage.appendChild(box)
}

async function renderPptx(bytes: ArrayBuffer, stage: HTMLElement, w: number, h: number) {
  const holder = el('div', 'pptx-stage')
  holder.style.width = `${Math.max(320, w)}px`
  stage.appendChild(holder)
  const previewer = initPptx(holder, { width: Math.max(320, w), height: Math.max(240, h / 1.4), mode: 'slide' })
  await (previewer as any).preview(bytes)
}

/** odp/odt: build DOM strictly via textContent — injection-free by construction */
async function renderOdf(bytes: ArrayBuffer, stage: HTMLElement, kind: 'odp' | 'odt') {
  const zip = await JSZip.loadAsync(bytes)
  const entry = zip.file('content.xml')
  if (!entry) throw new Error('ODF 內容缺失')
  const xml = await entry.async('string')
  const doc = new DOMParser().parseFromString(xml, 'text/xml')
  if (kind === 'odp') {
    const pages = doc.getElementsByTagName('draw:page')
    if (!pages.length) throw new Error('無簡報頁面')
    for (let i = 0; i < pages.length; i++) {
      const slide = el('section', 'slide-card')
      slide.appendChild(el('div', 'slide-no', `${i + 1} / ${pages.length}`))
      const texts = pages[i].getElementsByTagName('text:p')
      for (let t = 0; t < texts.length; t++) {
        const val = texts[t].textContent || ''
        if (val.trim()) slide.appendChild(el('p', 'slide-text', val))
      }
      stage.appendChild(slide)
    }
  } else {
    const body = doc.getElementsByTagName('office:text')[0]
    if (!body) throw new Error('無文件正文')
    const kids = body.children
    for (let i = 0; i < kids.length; i++) {
      const tag = kids[i].tagName
      if (tag === 'text:h' || tag === 'text:p') {
        const val = kids[i].textContent || ''
        if (val.trim()) stage.appendChild(el(tag === 'text:h' ? 'h2' : 'p', '', val))
      }
    }
  }
}

const stage = document.getElementById('stage')

function parent_() { return window.parent }

if (stage) {
  parent_().postMessage({ type: 'office-ready' }, '*')
  window.addEventListener('message', async (ev) => {
    const d = ev.data
    if (!d || d.type !== 'office-render' || !stage) return
    try {
      stage.innerHTML = ''
      const bytes: ArrayBuffer = d.bytes
      if (d.kind === 'docx') await renderDocx(bytes, stage)
      else if (d.kind === 'pptx') await renderPptx(bytes, stage, d.width || stage.clientWidth, d.height || 540)
      else if (d.kind === 'odp' || d.kind === 'odt') await renderOdf(bytes, stage, d.kind)
      else throw new Error('不支援的類型')
      parent_().postMessage({ type: 'office-ok', chars: stage.textContent?.length || 0,
        sample: (stage.textContent || '').trim().slice(0, 60) }, '*')
    } catch (e) {
      parent_().postMessage({ type: 'office-err', msg: String((e as Error)?.message || e) }, '*')
    }
  })
}
