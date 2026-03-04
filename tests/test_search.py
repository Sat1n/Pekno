import asyncio
import sys
import os

# 确保能找到 hub 包
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hub.core.search import SearchService

async def test_search():
    search = SearchService()
    queries = ["照片管理", "BettaFish", "二次元", "immich"]
    
    for q in queries:
        print(f"\n🔎 搜索词: 【{q}】")
        
        # 测试纯向量搜索
        print("--- 纯向量搜索 (语义理解) ---")
        v_results = await search.vector_search(q, limit=2)
        for item, score in v_results:
            print(f"[{score:.4f}] {item.title}")
            
        # 测试混合搜索
        print("--- 混合搜索 (精确匹配+语义) ---")
        h_results = await search.hybrid_search(q, limit=2)
        if not h_results:
            print("  (未匹配到关键词)")
        for item, v_score, t_score in h_results:
            print(f"[{v_score:.4f} + {t_score:.4f} = {v_score + t_score:.4f}] {item.title}")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(test_search())