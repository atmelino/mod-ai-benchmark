import sys

from ai_benchmark import AIBenchmark
# benchmark = AIBenchmark(verbose_level=3)
# results = benchmark.run()
print(f"Python {sys.version}")

results = AIBenchmark().run()

