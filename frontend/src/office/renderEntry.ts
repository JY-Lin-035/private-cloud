/* Sandbox-frame office renderer. Runs ONLY inside /office/host.html which the
 * parent embeds with sandbox="allow-scripts" (opaque origin: no cookies, no
 * parent DOM, no network by meta CSP). Bundled to public/office/render.js. */
import JSZip from 'jszip'
import mammoth from 'mammoth/mammoth.browser'
import { init as initPptx } from 'pptx-preview'
import DOMPurify from 'dompurify'
import { getDocument } from 'pdfjs-dist'
// Sandboxed (opaque-origin) frames cannot load blob/module workers under strict
// CSP. Bundle the worker into this script and hand it to pdf.js via the
// documented `globalThis.pdfjsWorker` hook -> pdf.js runs a main-thread fake
// worker, no Worker() and no dynamic import ever happens.
import * as pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs'
;(globalThis as unknown as { pdfjsWorker: unknown }).pdfjsWorker = pdfjsWorker

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

async function renderPdf(bytes: ArrayBuffer, stage: HTMLElement): Promise<number> {
  const doc = await getDocument({ data: new Uint8Array(bytes), disableFontFace: true } as any).promise
  const pages = Math.min(doc.numPages, 40)
  const targetW = Math.max(320, stage.clientWidth - 32)
  for (let i = 1; i <= pages; i++) {
    const page = await doc.getPage(i)
    const vp0 = page.getViewport({ scale: 1 })
    const scale = Math.min(2.5, targetW / vp0.width)
    const vp = page.getViewport({ scale })
    const canvas = document.createElement('canvas')
    canvas.width = Math.floor(vp.width)
    canvas.height = Math.floor(vp.height)
    canvas.className = 'pdf-page'
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('canvas 不可用')
    await page.render({ canvasContext: ctx, viewport: vp, canvas } as any).promise
    const img = document.createElement('img')
    img.src = canvas.toDataURL('image/jpeg', 0.82)
    img.alt = `第 ${i} 頁`
    stage.appendChild(img)
  }
  if (doc.numPages > pages) {
    stage.appendChild(el('p', 'pdf-more', `僅預覽前 ${pages} 頁（共 ${doc.numPages} 頁），完整內容請下載查看`))
  }
  return pages
}

const stage = document.getElementById('stage')

function parent_() { return window.parent }

if (stage) {
  parent_().postMessage({ type: 'office-ready' }, '*')
  const lastJob = { kind: '', bytes: null as ArrayBuffer | null, width: 0, height: 0 }

  async function runRender(): Promise<number> {
    if (!stage || !lastJob.bytes || !lastJob.kind) return 0
    stage.innerHTML = ''
    if (lastJob.kind === 'docx') { await renderDocx(lastJob.bytes, stage); return 0 }
    if (lastJob.kind === 'pptx') { await renderPptx(lastJob.bytes, stage, lastJob.width, lastJob.height); return 0 }
    if (lastJob.kind === 'odp' || lastJob.kind === 'odt') { await renderOdf(lastJob.bytes, stage, lastJob.kind as 'odp' | 'odt'); return 0 }
    if (lastJob.kind === 'pdf') return renderPdf(lastJob.bytes, stage)
    throw new Error('不支援的類型')
  }

  window.addEventListener('message', async (ev) => {
    const d = ev.data
    if (!d || !stage) return
    try {
      if (d.type === 'office-render') {
        lastJob.kind = d.kind
        lastJob.bytes = d.bytes
        lastJob.width = d.width || stage.clientWidth || 900
        lastJob.height = d.height || 560
        const pages = await runRender()
        parent_().postMessage({ type: 'office-ok', kind: d.kind, pages,
          chars: stage.textContent?.length || 0,
          sample: (stage.textContent || '').trim().slice(0, 60) }, '*')
      } else if (d.type === 'office-resize') {
        if (!lastJob.bytes || (d.width === lastJob.width && d.height === lastJob.height)) return
        lastJob.width = d.width; lastJob.height = d.height
        if (lastJob.kind === 'pptx') { await runRender() } // pptx needs remount on size change; others reflow
        parent_().postMessage({ type: 'office-ok', kind: lastJob.kind, chars: stage.textContent?.length || 0 }, '*')
      }
    } catch (e) {
      parent_().postMessage({ type: 'office-err', msg: String((e as Error)?.message || e) }, '*')
    }
  })
}
