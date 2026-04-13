import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN.json'
import en from './en.json'

export const APP_LOCALE_KEY = 'pekno-locale'
export const SUPPORTED_LOCALES = ['zh-CN', 'en'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]

function normalizeLocale(input?: string | null): AppLocale {
  const value = String(input || '').trim().toLowerCase()
  if (value === 'zh' || value.startsWith('zh-cn') || value.startsWith('zh-hans')) {
    return 'zh-CN'
  }
  if (value.startsWith('en')) {
    return 'en'
  }
  return 'en'
}

export function detectInitialLocale(): AppLocale {
  if (typeof window === 'undefined') {
    return 'en'
  }

  const saved = window.localStorage.getItem(APP_LOCALE_KEY)
  if (saved) {
    return normalizeLocale(saved)
  }

  const browserLocale =
    window.navigator.languages?.find(Boolean) ||
    window.navigator.language ||
    'en'
  return normalizeLocale(browserLocale)
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectInitialLocale(),
  fallbackLocale: 'en',
  messages: {
    'zh-CN': zhCN,
    en,
  },
})

export function setAppLocale(locale: string) {
  const normalized = normalizeLocale(locale)
  i18n.global.locale.value = normalized
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(APP_LOCALE_KEY, normalized)
  }
  return normalized
}

export function getAppLocale() {
  return i18n.global.locale.value as AppLocale
}

export default i18n
