from __future__ import annotations

import re
from typing import Final

ERR_UNAUTHORIZED: Final = "ERR_UNAUTHORIZED"
ERR_FORBIDDEN: Final = "ERR_FORBIDDEN"
ERR_NOT_FOUND: Final = "ERR_NOT_FOUND"
ERR_INVALID_INPUT: Final = "ERR_INVALID_INPUT"
ERR_VALIDATION_FAILED: Final = "ERR_VALIDATION_FAILED"
ERR_INTERNAL_SERVER_ERROR: Final = "ERR_INTERNAL_SERVER_ERROR"
ERR_QUOTA_EXCEEDED: Final = "ERR_QUOTA_EXCEEDED"
ERR_UPLOAD_UNSUPPORTED_TYPE: Final = "ERR_UPLOAD_UNSUPPORTED_TYPE"
ERR_PLUGIN_NOT_FOUND: Final = "ERR_PLUGIN_NOT_FOUND"
ERR_NOTIFICATION_NOT_FOUND: Final = "ERR_NOTIFICATION_NOT_FOUND"
ERR_VAULT_CATEGORY_EXISTS: Final = "ERR_VAULT_CATEGORY_EXISTS"
ERR_INVALID_CREDENTIALS: Final = "ERR_INVALID_CREDENTIALS"
ERR_CREDENTIAL_UNREADABLE: Final = "ERR_CREDENTIAL_UNREADABLE"
ERR_INVITE_INVALID: Final = "ERR_INVITE_INVALID"
ERR_USER_EXISTS: Final = "ERR_USER_EXISTS"
ERR_ITEM_NOT_FOUND: Final = "ERR_ITEM_NOT_FOUND"
ERR_CATEGORY_NOT_FOUND: Final = "ERR_CATEGORY_NOT_FOUND"

_EXACT_DETAIL_MAP: dict[str, tuple[str, str]] = {
    "系统已初始化，禁止再次创建超级管理员。": (ERR_FORBIDDEN, "The system has already been initialized."),
    "用户名已存在": (ERR_USER_EXISTS, "This username already exists."),
    "邀请码无效或已被使用": (ERR_INVITE_INVALID, "The invitation code is invalid or has already been used."),
    "用户名或密码错误": (ERR_INVALID_CREDENTIALS, "Incorrect username or password."),
    "用户不存在": (ERR_NOT_FOUND, "The requested user could not be found."),
    "当前密码错误": (ERR_INVALID_INPUT, "The current password is incorrect."),
    "令牌不存在": (ERR_NOT_FOUND, "The requested token could not be found."),
    "无法验证登录凭证": (ERR_UNAUTHORIZED, "Unable to validate the login credentials."),
    "仅管理员可以执行该操作": (ERR_FORBIDDEN, "Only administrators can perform this action."),
    "条目不存在或您无权访问": (ERR_ITEM_NOT_FOUND, "The requested item does not exist or you do not have access to it."),
    "当前仅支持上传图片类型的注释资产": (ERR_INVALID_INPUT, "Only image annotation assets are supported."),
    "上传内容为空": (ERR_INVALID_INPUT, "The uploaded content is empty."),
    "rect_norm 不是合法 JSON": (ERR_INVALID_INPUT, "rect_norm must be valid JSON."),
    "当前仅支持 PNG、JPG/JPEG、WEBP、BMP 静态图片上传。": (ERR_UPLOAD_UNSUPPORTED_TYPE, "Only static PNG, JPG/JPEG, WEBP, and BMP images are supported."),
    "GIF 动图暂不支持上传，请改用静态图片格式。": (ERR_UPLOAD_UNSUPPORTED_TYPE, "GIF uploads are not supported. Please use a static image format."),
    "当前仅支持 MP4、WEBM、MOV、M4V、MKV、AVI 等常见视频格式。": (ERR_UPLOAD_UNSUPPORTED_TYPE, "Only common video formats such as MP4, WEBM, MOV, M4V, MKV, and AVI are supported."),
    "当前仅支持 MP3、WAV、M4A、AAC、FLAC、OGG、WEBM 等常见音频格式。": (ERR_UPLOAD_UNSUPPORTED_TYPE, "Only common audio formats such as MP3, WAV, M4A, AAC, FLAC, OGG, and WEBM are supported."),
    "当前仅支持 DOCX，其他 Office 文档请先转换为 PDF、TXT 或 Markdown。": (ERR_UPLOAD_UNSUPPORTED_TYPE, "Only DOCX is supported. Please convert other Office files to PDF, TXT, or Markdown first."),
    "当前仅支持静态图片、常见视频音频、PDF、TXT、Markdown 与 DOCX 上传。": (ERR_UPLOAD_UNSUPPORTED_TYPE, "Only static images, common video/audio formats, PDF, TXT, Markdown, and DOCX uploads are supported."),
    "通知不存在": (ERR_NOTIFICATION_NOT_FOUND, "The notification could not be found."),
    "分类名称不能为空": (ERR_INVALID_INPUT, "The category name cannot be empty."),
    "“未分类”是系统保留名称": (ERR_INVALID_INPUT, "\"Uncategorized\" is a reserved system name."),
    "该分类名称已存在": (ERR_VAULT_CATEGORY_EXISTS, "A category with this name already exists."),
    "分类不存在": (ERR_CATEGORY_NOT_FOUND, "The requested category could not be found."),
    "未找到 manifest.json 描述文件": (ERR_INVALID_INPUT, "The uploaded plugin package does not contain a manifest.json file."),
    "安装会话已过期，请重新上传": (ERR_INVALID_INPUT, "The installation session has expired. Please upload the package again."),
    "Manifest 缺少插件 ID": (ERR_INVALID_INPUT, "The plugin manifest is missing a plugin ID."),
    "service 必须为 hub、worker 或 scheduler": (ERR_INVALID_INPUT, "The service must be one of hub, worker, or scheduler."),
    "assignments 必须为数组": (ERR_INVALID_INPUT, "assignments must be an array."),
}

_REGEX_DETAIL_MAP: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"^未找到插件[:：]\s*(.+)$"), ERR_PLUGIN_NOT_FOUND, "Plugin not found: {match}"),
    (re.compile(r"^找不到插件[:：]\s*(.+)$"), ERR_PLUGIN_NOT_FOUND, "Plugin not found: {match}"),
    (re.compile(r"^插件\s+(.+)\s+不支持单条解析$"), ERR_INVALID_INPUT, "Plugin {match} does not support single-item parsing."),
    (re.compile(r"^目标分类不存在$"), ERR_CATEGORY_NOT_FOUND, "The target category does not exist."),
    (re.compile(r"^当前用户无权操作该条目$"), ERR_FORBIDDEN, "You do not have permission to operate on this item."),
    (re.compile(r"^当前用户无权访问该条目$"), ERR_FORBIDDEN, "You do not have permission to access this item."),
]

_DEFAULT_STATUS_MAP: dict[int, tuple[str, str]] = {
    400: (ERR_INVALID_INPUT, "The request is invalid."),
    401: (ERR_UNAUTHORIZED, "Authentication is required for this request."),
    403: (ERR_FORBIDDEN, "You do not have permission to perform this action."),
    404: (ERR_NOT_FOUND, "The requested resource could not be found."),
    409: (ERR_INVALID_INPUT, "The request conflicts with the current resource state."),
    422: (ERR_VALIDATION_FAILED, "Request validation failed."),
    500: (ERR_INTERNAL_SERVER_ERROR, "An internal server error occurred."),
}


def resolve_error_code_and_detail(status_code: int, detail: object) -> tuple[str, str]:
    if isinstance(detail, str):
        exact = _EXACT_DETAIL_MAP.get(detail)
        if exact:
            return exact
        for pattern, code, template in _REGEX_DETAIL_MAP:
            match = pattern.match(detail)
            if match:
                dynamic = match.group(1) if match.groups() else detail
                return code, template.format(match=dynamic)
        if re.search(r"[\u4e00-\u9fff]", detail):
            return _DEFAULT_STATUS_MAP.get(status_code, (ERR_INTERNAL_SERVER_ERROR, "The request failed."))
        return _DEFAULT_STATUS_MAP.get(status_code, (ERR_INTERNAL_SERVER_ERROR, detail if detail else "The request failed."))
    return _DEFAULT_STATUS_MAP.get(status_code, (ERR_INTERNAL_SERVER_ERROR, "The request failed."))
