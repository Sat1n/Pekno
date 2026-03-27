# =========================================================================
# 【多模态/多版本硬件兼容架构说明】
# 为适应不同显卡（如老架构 6G 显存 / 新架构），我们采用多标签镜像隔离构建策略：
#
# 1. 默认构建 (latest) -> 最新版 ctranslate2 / faster-whisper
# FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04
#
# 2. 老硬件向后兼容版本 (cu12d8:latest) -> 锁定 ctranslate2==4.4.0 (支持 CUDA 12 + cudnn 8)
# FROM nvidia/cuda:12.x.x-cudnn8-runtime-ubuntu22.04
# 
# 3. 极旧硬件兼容版本 (cu11d8:latest) -> 锁定 ctranslate2==3.24.0 (支持 CUDA 11 + cudnn 8)
# FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04
# =========================================================================

# TODO: 生产环境部署时，确保系统层包含多媒体引擎和 JS 运行时
# RUN apt-get update && apt-get install -y ffmpeg nodejs
