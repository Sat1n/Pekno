<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { register, resolveApiErrorMessage, setStoredToken } from '@/lib/api'

const router = useRouter()
const { t } = useI18n()
const username = ref('')
const password = ref('')
const inviteCode = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)

async function submitRegister() {
  errorMessage.value = ''
  isSubmitting.value = true
  try {
    const result = await register({
      username: username.value.trim(),
      password: password.value,
      invite_code: inviteCode.value.trim(),
    })
    setStoredToken(result.access_token)
    await router.replace('/')
  } catch (error: any) {
    errorMessage.value = resolveApiErrorMessage(error, 'auth.registerFailed')
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.12),_transparent_35%),linear-gradient(180deg,_rgba(248,250,252,1)_0%,_rgba(241,245,249,1)_100%)] flex items-center justify-center px-6">
    <Card class="w-full max-w-md border-border/70 shadow-2xl bg-background/95 backdrop-blur">
      <CardHeader class="space-y-2">
        <CardTitle class="text-2xl font-bold">{{ t('auth.registerTitle') }}</CardTitle>
        <CardDescription>{{ t('auth.registerDescription') }}</CardDescription>
      </CardHeader>
      <CardContent>
        <form class="space-y-5" @submit.prevent="submitRegister">
          <div class="space-y-2">
            <Label for="register-invite">{{ t('auth.inviteCode') }}</Label>
            <Input id="register-invite" v-model="inviteCode" placeholder="IRIS-AB12-CD34" minlength="6" maxlength="128" required />
          </div>
          <div class="space-y-2">
            <Label for="register-username">{{ t('auth.username') }}</Label>
            <Input id="register-username" v-model="username" placeholder="your-name" minlength="3" maxlength="64" required />
          </div>
          <div class="space-y-2">
            <Label for="register-password">{{ t('auth.password') }}</Label>
            <Input id="register-password" v-model="password" type="password" minlength="8" maxlength="128" required />
          </div>
          <p v-if="errorMessage" class="text-sm text-destructive">{{ errorMessage }}</p>
          <Button type="submit" class="w-full" :disabled="isSubmitting">
            {{ isSubmitting ? t('auth.registering') : t('auth.register') }}
          </Button>
        </form>
        <div class="mt-5 border-t pt-4 text-sm text-muted-foreground flex items-center justify-between">
          <span>{{ t('auth.alreadyHaveAccount') }}</span>
          <button class="font-medium text-primary hover:underline" @click="router.push('/login')">
            {{ t('auth.backToLogin') }}
          </button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
