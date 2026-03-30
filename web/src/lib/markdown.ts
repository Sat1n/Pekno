import MarkdownIt from 'markdown-it'
import markdownItAnchor from 'markdown-it-anchor'
import markdownItTaskLists from 'markdown-it-task-lists'
import MarkdownItGitHubAlerts from 'markdown-it-github-alerts'
import DOMPurify from 'dompurify'
import { createHighlighter, type BundledLanguage, type BundledTheme, type Highlighter } from 'shiki'

export type MarkdownTheme = 'light' | 'dark'
export type MarkdownMode = 'readme' | 'summary'

const supportedLanguages = [
  'md',
  'markdown',
  'js',
  'javascript',
  'jsx',
  'ts',
  'typescript',
  'tsx',
  'json',
  'bash',
  'shell',
  'sh',
  'python',
  'yaml',
  'toml',
  'docker',
  'dockerfile',
  'go',
  'rust',
  'java',
  'html',
  'css',
] as const satisfies readonly BundledLanguage[]

const supportedThemes = ['github-light', 'github-dark'] as const satisfies readonly BundledTheme[]

const languageAlias: Record<string, BundledLanguage> = {
  txt: 'md',
  yml: 'yaml',
  py: 'python',
  rs: 'rust',
  zsh: 'bash',
  xml: 'html',
}

const headingAnchorSymbol = `<span aria-hidden="true">#</span>`

let highlighterPromise: Promise<Highlighter> | null = null

function getHighlighter() {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: [...supportedThemes],
      langs: [...supportedLanguages],
    })
  }
  return highlighterPromise
}

function normalizeLanguage(language?: string) {
  const normalized = String(language || '').trim().toLowerCase()
  if (!normalized) return 'md' as BundledLanguage
  if ((supportedLanguages as readonly string[]).includes(normalized)) {
    return normalized as BundledLanguage
  }
  return languageAlias[normalized] || ('md' as BundledLanguage)
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function createMarkdownRenderer(highlighter: Highlighter, theme: MarkdownTheme) {
  const shikiTheme: BundledTheme = theme === 'dark' ? 'github-dark' : 'github-light'

  const markdown = new MarkdownIt({
    html: true,
    linkify: true,
    breaks: true,
    typographer: true,
    highlight(code, language): string {
      const lang = normalizeLanguage(language)

      try {
        return highlighter.codeToHtml(code, {
          lang,
          theme: shikiTheme,
        })
      } catch {
        const escaped = escapeHtml(code)
        return `<pre class="vault-shiki-fallback"><code>${escaped}</code></pre>`
      }
    },
  })

  markdown.enable(['table', 'strikethrough'])
  markdown.use(markdownItTaskLists, { enabled: true, label: true, labelAfter: true })
  markdown.use(MarkdownItGitHubAlerts)
  markdown.use(markdownItAnchor, {
    level: [2, 3, 4],
    permalink: markdownItAnchor.permalink.ariaHidden({
      placement: 'before',
      class: 'vault-heading-anchor',
      symbol: headingAnchorSymbol,
    }),
  })

  const defaultLinkOpen =
    markdown.renderer.rules.link_open ??
    ((tokens: any[], idx: number, options: unknown, _env: unknown, self: any) =>
      self.renderToken(tokens, idx, options))

  markdown.renderer.rules.link_open = (tokens: any[], idx: number, options: unknown, env: unknown, self: any) => {
    const targetIndex = tokens[idx]?.attrIndex('target') ?? -1
    if (targetIndex < 0) {
      tokens[idx]?.attrPush(['target', '_blank'])
    } else {
      tokens[idx]?.attrs?.[targetIndex]?.splice(1, 1, '_blank')
    }

    const relIndex = tokens[idx]?.attrIndex('rel') ?? -1
    if (relIndex < 0) {
      tokens[idx]?.attrPush(['rel', 'noopener noreferrer'])
    } else {
      tokens[idx]?.attrs?.[relIndex]?.splice(1, 1, 'noopener noreferrer')
    }

    return defaultLinkOpen(tokens, idx, options as any, env, self)
  }

  return markdown
}

function sanitizeHtml(content: string) {
  return DOMPurify.sanitize(content, {
    USE_PROFILES: { html: true, svg: true, svgFilters: true },
    ADD_ATTR: [
      'class',
      'style',
      'target',
      'rel',
      'align',
      'id',
      'tabindex',
      'aria-hidden',
      'aria-label',
      'aria-describedby',
      'checked',
      'disabled',
      'type',
      'role',
      'dir',
    ],
    ALLOW_DATA_ATTR: true,
  })
}

export async function renderMarkdown(
  content: string,
  theme: MarkdownTheme = 'light',
  _mode: MarkdownMode = 'readme',
) {
  const normalized = String(content || '').replace(/\\n/g, '\n')
  const highlighter = await getHighlighter()
  const markdown = createMarkdownRenderer(highlighter, theme)
  const rendered = markdown.render(normalized)
  return sanitizeHtml(rendered)
}
