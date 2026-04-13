<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { initializeAuth, resolveApiErrorMessage, setStoredToken } from '@/lib/api'
import { resolveAuthStatus } from '@/router'

const router = useRouter()
const { t } = useI18n()
const username = ref('')
const password = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)

async function submitInit() {
  errorMessage.value = ''
  isSubmitting.value = true
  try {
    const result = await initializeAuth({
      username: username.value.trim(),
      password: password.value,
    })
    setStoredToken(result.access_token)
    await resolveAuthStatus(true)
    await router.replace('/?openSettings=models')
  } catch (error: any) {
    errorMessage.value = resolveApiErrorMessage(error, 'auth.initFailed')
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-background flex items-center justify-center px-6">
    <Card class="w-full max-w-md border-border shadow-xl">
      <CardHeader class="space-y-2">
        <CardTitle class="text-2xl font-bold">{{ t('auth.initTitle') }}</CardTitle>
        <CardDescription>{{ t('auth.initDescription') }}</CardDescription>
      </CardHeader>
      <CardContent>
        <form class="space-y-5" @submit.prevent="submitInit">
          <div class="space-y-2">
            <Label for="init-username">{{ t('auth.username') }}</Label>
            <Input id="init-username" v-model="username" placeholder="super-admin" minlength="3" maxlength="64" required />
          </div>
          <div class="space-y-2">
            <Label for="init-password">{{ t('auth.password') }}</Label>
            <Input id="init-password" v-model="password" type="password" minlength="8" maxlength="128" required />
          </div>
          <p v-if="errorMessage" class="text-sm text-destructive">{{ errorMessage }}</p>
          <Button type="submit" class="w-full" :disabled="isSubmitting">
            {{ isSubmitting ? t('auth.initializing') : t('auth.finishInit') }}
          </Button>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
