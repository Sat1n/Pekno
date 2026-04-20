import {
  getDocument,
  GlobalWorkerOptions,
  TextLayerImages,
  type PDFDocumentProxy,
  type PDFPageProxy,
} from 'pdfjs-dist'
import { TextLayerBuilder } from 'pdfjs-dist/web/pdf_viewer.mjs'

import 'pdfjs-dist/web/pdf_viewer.css'

const workerUrl = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url)
workerUrl.searchParams.set('v', 'pekno-mjs-mime')
GlobalWorkerOptions.workerSrc = workerUrl.toString()

export { getDocument, TextLayerBuilder, TextLayerImages }
export type { PDFDocumentProxy, PDFPageProxy }
