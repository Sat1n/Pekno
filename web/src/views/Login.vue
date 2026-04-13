<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { login, resolveApiErrorMessage, setStoredToken } from '@/lib/api'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const username = ref('')
const password = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)

async function submitLogin() {
  errorMessage.value = ''
  isSubmitting.value = true
  try {
    const result = await login({
      username: username.value.trim(),
      password: password.value,
    })
    setStoredToken(result.access_token)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (error: any) {
    errorMessage.value = resolveApiErrorMessage(error, 'auth.loginFailed')
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.12),_transparent_35%),linear-gradient(180deg,_rgba(248,250,252,1)_0%,_rgba(241,245,249,1)_100%)] flex items-center justify-center px-6">
    <Card class="w-full max-w-md border-border/70 shadow-2xl bg-background/95 backdrop-blur">
      <CardHeader class="space-y-2">
        <CardTitle class="text-2xl font-bold">{{ t('auth.loginTitle') }}</CardTitle>
        <CardDescription>{{ t('auth.loginDescription') }}</CardDescription>
      </CardHeader>
      <CardContent>
        <form class="space-y-5" @submit.prevent="submitLogin">
          <div class="space-y-2">
            <Label for="login-username">{{ t('auth.username') }}</Label>
            <Input id="login-username" v-model="username" placeholder="admin" minlength="3" maxlength="64" required />
          </div>
          <div class="space-y-2">
            <Label for="login-password">{{ t('auth.password') }}</Label>
            <Input id="login-password" v-model="password" type="password" minlength="8" maxlength="128" required />
          </div>
          <p v-if="errorMessage" class="text-sm text-destructive">{{ errorMessage }}</p>
          <Button type="submit" class="w-full" :disabled="isSubmitting">
            {{ isSubmitting ? t('auth.loggingIn') : t('auth.login') }}
          </Button>
        </form>
        <div class="mt-5 border-t pt-4 text-sm text-muted-foreground flex items-center justify-between">
          <span>{{ t('auth.haveInvite') }}</span>
          <button class="font-medium text-primary hover:underline" @click="router.push('/register')">
            {{ t('auth.goRegister') }}
          </button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
