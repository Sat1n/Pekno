import asyncio
from hub.core.search import SearchService

async def test_search():
    search = SearchService()
    
    # 尝试一些模糊的意图词
    queries = ["照片管理工具", "舆情分析助手", "二次元图片放大"]
    
    for q in queries:
        print(f"\n👉 搜索意图: {q}")
        results = await search.vector_search(q, limit=2)
        
        for item, score in results:
            print(f"🎯 [得分: {score:.4f}] {item.title}")
            print(f"📝 摘要预览: {item.summary[:60]}...")
            print("-" * 20)

if __name__ == "__main__":
    asyncio.run(test_search())