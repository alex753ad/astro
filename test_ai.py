import asyncio, httpx
async def test():
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get('http://localhost:8000/health/ai')
        print(r.text)
asyncio.run(test())
