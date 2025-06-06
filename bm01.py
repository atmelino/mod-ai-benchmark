import sys

from ai_benchmark import AIBenchmark

# benchmark = AIBenchmark(verbose_level=3)
# results = benchmark.run()
print(f"Python {sys.version}")

test_ids = [
    "3",
    "5",
]

results = AIBenchmark().run(test_ids=test_ids)
