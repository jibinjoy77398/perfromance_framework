"""
R&D only — controlled stress test against localhost.
Never use against servers you do not own.
"""
import asyncio
import time
import aiohttp

class DoSTester:
    def __init__(self, url: str, output_fn=print):
        self.url = url
        self.log = output_fn

    async def _single_request(self, session, results):
        start = time.monotonic()
        try:
            async with session.get(self.url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                elapsed = (time.monotonic() - start) * 1000
                results.append({"status": resp.status, "ms": elapsed, "error": None})
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            results.append({"status": 0, "ms": elapsed, "error": str(e)})

    async def run_wave(self, concurrency: int, duration_seconds: int = 10):
        """Fire `concurrency` parallel requests continuously for `duration_seconds`."""
        self.log(f"  🔴 DoS wave — {concurrency} persistent workers for {duration_seconds}s against {self.url}")
        results = []
        deadline = time.monotonic() + duration_seconds
        
        # Use a high-performance connector for massive concurrency
        connector = aiohttp.TCPConnector(limit=0, limit_per_host=0, force_close=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            
            async def worker():
                """A single worker that fires requests as fast as possible."""
                while time.monotonic() < deadline:
                    await self._single_request(session, results)
            
            # Spawn exactly 'concurrency' number of persistent workers
            workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
            
            # Wait for the deadline to pass
            await asyncio.sleep(duration_seconds)
            
            # Gracefully wait for workers to wrap up their last request (max 2s)
            pending = {t for t in workers if not t.done()}
            if pending:
                await asyncio.wait(pending, timeout=2.0)
            
        return self._summarise(results, concurrency, duration_seconds)

    async def run_ramp(self, levels=(10, 50, 100, 200, 500, 1000, 2000), duration_per_level=8):
        """Ramp up concurrency through levels and report where server degrades."""
        summary = []
        for level in levels:
            stats = await self.run_wave(level, duration_per_level)
            summary.append(stats)
            if not stats:
                self.log(f"    [{level:>4} req] No results — skipping level")
                continue
            self.log(
                f"    [{level:>4} req] "
                f"avg={stats['avg_ms']:.0f}ms  "
                f"p95={stats['p95_ms']:.0f}ms  "
                f"err={stats['error_rate_pct']:.1f}%  "
                f"rps={stats['rps']:.1f}"
            )
            if stats['error_rate_pct'] > 90:
                self.log(f"    ⚠️  Server breaking at {level} concurrent requests (90% error rate reached)")
                break
        return summary

    def _summarise(self, results, concurrency, duration):
        if not results:
            return {}
        ms_vals = sorted(r["ms"] for r in results)
        errors = sum(1 for r in results if r["error"] or r["status"] >= 500)
        n = len(results)
        p95_idx = int(0.95 * n)
        return {
            "concurrency": concurrency,
            "total_requests": n,
            "avg_ms": sum(ms_vals) / n,
            "p95_ms": ms_vals[min(p95_idx, n - 1)],
            "min_ms": ms_vals[0],
            "max_ms": ms_vals[-1],
            "error_rate_pct": (errors / n) * 100,
            "rps": n / max(duration, 1),
        }
