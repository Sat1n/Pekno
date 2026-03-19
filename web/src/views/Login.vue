<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { login, setStoredToken } from '@/lib/api'

const router = useRouter()
const route = useRoute()
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
    errorMessage.value = error?.response?.data?.detail || '登录失败，请检查账号密码。'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-background flex items-center justify-center px-6">
    <Card class="w-full max-w-md border-border shadow-xl">
      <CardHeader class="space-y-2">
        <CardTitle class="text-2xl font-bold">登录 Pekno</CardTitle>
        <CardDescription>输入管理员账号后进入你的信息中枢。</CardDescription>
      </CardHeader>
      <CardContent>
        <form class="space-y-5" @submit.prevent="submitLogin">
          <div class="space-y-2">
            <Label for="login-username">账号</Label>
            <Input id="login-username" v-model="username" placeholder="admin" minlength="3" maxlength="64" required />
          </div>
          <div class="space-y-2">
            <Label for="login-password">密码</Label>
            <Input id="login-password" v-model="password" type="password" minlength="8" maxlength="128" required />
          </div>
          <p v-if="errorMessage" class="text-sm text-destructive">{{ errorMessage }}</p>
          <Button type="submit" class="w-full" :disabled="isSubmitting">
            {{ isSubmitting ? '登录中...' : '登录' }}
          </Button>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
