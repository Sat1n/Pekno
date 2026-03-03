import pytest
from datetime import datetime
from hub.core.models import UniversalItem, ItemIntent

def test_bilibili_ingestion():
    # 模拟插件抓取的原始数据
    raw_bili_data = {
        "bv_id": "BV1yx411c79x",
        "owner": {"name": "老番茄"},
        "title": "这是一段非常有意思的科技评测视频",
        "pubdate": 1709450400,  # 时间戳
        "desc": "今天我们来聊聊 2026 年的个人 AI 助手...",
        "pic": "https://i0.hdslb.com/bfs/archive/cover.jpg"
    }

    # 模拟插件内的 transform 逻辑
    try:
        item = UniversalItem(
            id=f"bili_{raw_bili_data['bv_id']}",
            title=raw_bili_data['title'],
            source_type="bilibili",
            created_at=datetime.fromtimestamp(raw_bili_data['pubdate']),
            raw_link=f"https://www.bilibili.com/video/{raw_bili_data['bv_id']}",
            intent=ItemIntent.video,
            content_text=raw_bili_data['desc'],
            cover_url=raw_bili_data['pic'],
            capabilities=["summarize", "preview"],
            metadata_extra={"up": raw_bili_data['owner']['name']}
        )
        print("\n✅ 数据契约校验通过！")
        print(f"Iris 识别到的标题: {item.title}")
        print(f"自动转换的时间: {item.created_at}")
    except Exception as e:
        pytest.fail(f"❌ 数据契约校验失败: {e}")

if __name__ == "__main__":
    test_bilibili_ingestion()